"""经营明细导入/归并/发布/报告取数的端到端业务规则测试。

覆盖需求核对点：
- 重复文件导入幂等，不增加经营金额；
- 跨源同号异值产生冲突候选，不重复累计、不静默覆盖，未裁决不参与汇总；
- 无效金额、缺业务编号/周期可定位到原始文件，不当零值；
- 币种不一致的金额不直接相加，按周期+币种分别汇总；
- 发布生成不可变版本，中断重试不留半批（解析失败零写入）；
- 报告快照绑定数据版本、来源范围与未计入冲突项，后续导入不改写历史报告；
- 每条明细可追溯来源、原始行与归并依据。

直接用标准库 unittest 跑 service 层，不依赖外部测试框架：
    backend/.venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from decimal import Decimal

# 兼容 python -I 隔离模式：显式把 backend 根目录加入模块搜索路径
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.detail_store import detail_store
from app.services.detail_import import (
    CANDIDATE_ACTIVE,
    CANDIDATE_CONFLICT,
    CANDIDATE_DUPLICATE,
    GROUP_CONFLICT,
    GROUP_CONSISTENT,
    GROUP_RESOLVED,
    DetailImportService,
)
from app.services.detail_parser import FileParseError, parse_detail_file
from app.services.report_snapshot import ReportSnapshotService

HEADER = "业务编号,所属周期,金额,币种"


def csv_file(*lines: str) -> str:
    return "\n".join([HEADER, *lines]) + "\n"


class DetailImportTests(unittest.TestCase):
    def setUp(self) -> None:
        detail_store.reset()
        self.importer = DetailImportService()
        self.reporter = ReportSnapshotService()

    # ------------------------------------------------------------ 解析与行级校验
    def test_invalid_amount_and_missing_fields_keep_location(self) -> None:
        content = csv_file(
            "BIZ-001,2026-01,100.00,CNY",
            "BIZ-002,2026-01,abc,CNY",        # 无效金额
            "BIZ-003,2026-01,,CNY",           # 空金额
            ",2026-01,50.00,CNY",             # 缺业务编号
            "BIZ-005,,50.00,CNY",             # 缺周期
            "BIZ-006,2026-01,NaN,CNY",        # 非有限数
        )
        parsed = parse_detail_file(content)
        self.assertEqual(len(parsed["valid_rows"]), 1)
        self.assertEqual(len(parsed["invalid_rows"]), 5)

        invalid = parsed["invalid_rows"]
        self.assertEqual([row["line_no"] for row in invalid], [3, 4, 5, 6, 7])
        bad_amount = invalid[0]
        self.assertIn("无效金额", " ".join(bad_amount["reasons"]))
        self.assertEqual(bad_amount["original_line"], "BIZ-002,2026-01,abc,CNY")
        missing_no = invalid[2]
        self.assertIn("业务编号", " ".join(missing_no["reasons"]))
        # 无效行绝不携带金额进入有效集合
        self.assertEqual(parsed["valid_rows"][0]["biz_no"], "BIZ-001")
        self.assertEqual(parsed["valid_rows"][0]["amount"], Decimal("100.00"))

    def test_header_alias_and_thousands_separator(self) -> None:
        content = "编号,账期,发生额,币别\nBIZ-001,2026-01,\"1,200.50\",cny\n"
        parsed = parse_detail_file(content)
        self.assertEqual(len(parsed["valid_rows"]), 1)
        row = parsed["valid_rows"][0]
        self.assertEqual(row["amount"], Decimal("1200.50"))
        self.assertEqual(row["currency"], "CNY")

    def test_empty_and_bad_header_rejected(self) -> None:
        with self.assertRaises(FileParseError):
            parse_detail_file("")
        with self.assertRaises(FileParseError):
            parse_detail_file("编号,周期,金额\nBIZ-001,2026-01,100\n")

    # ------------------------------------------------------------ 重复文件幂等
    def test_duplicate_file_import_is_idempotent(self) -> None:
        content = csv_file(
            "BIZ-001,2026-01,100.00,CNY",
            "BIZ-002,2026-01,200.00,CNY",
        )
        first = self.importer.import_file(
            filename="a.csv", content=content, source_name="门店A"
        )
        second = self.importer.import_file(
            filename="a-copy.csv", content=content, source_name="门店A"
        )
        self.assertFalse(first["deduplicated"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(len(detail_store.import_batches), 1)
        self.assertEqual(len(detail_store.source_files), 1)

        groups = self.importer.list_groups()
        self.assertEqual(len(groups), 2)
        dataset, _ = self.importer.publish_dataset()
        # 重复导入后金额仍是 300，不是 600
        cny_total = sum(
            (Decimal(item["amount"]) for item in dataset["summaries"] if item["currency"] == "CNY"),
            Decimal("0"),
        )
        self.assertEqual(cny_total, Decimal("300.00"))

    def test_same_content_other_source_keeps_provenance_but_no_double_sum(self) -> None:
        content = csv_file("BIZ-001,2026-01,100.00,CNY")
        first = self.importer.import_file(
            filename="a.csv", content=content, source_name="门店A"
        )
        other = self.importer.import_file(
            filename="a.csv", content=content, source_name="门店B"
        )
        repeat = self.importer.import_file(
            filename="a2.csv", content=content, source_name="门店A"
        )
        self.assertFalse(first["deduplicated"])
        # 不同来源的同内容文件要登记来源，不做全局去重
        self.assertFalse(other["deduplicated"])
        # 相同来源重复导入仍然幂等
        self.assertTrue(repeat["deduplicated"])
        self.assertEqual(len(detail_store.import_batches), 2)

        group = self.importer.list_groups()[0]
        self.assertEqual(group["status"], GROUP_CONSISTENT)
        self.assertEqual(len(group["candidates"]), 2)
        roles = [c["role"] for c in group["candidates"]]
        self.assertEqual(roles.count(CANDIDATE_ACTIVE), 1)
        self.assertEqual(roles.count(CANDIDATE_DUPLICATE), 1)
        dataset, _ = self.importer.publish_dataset()
        # 跨源同值去重，金额只算一次
        self.assertEqual(Decimal(dataset["summaries"][0]["amount"]), Decimal("100.00"))
        self.assertEqual(dataset["record_count"], 1)

    def test_in_file_duplicate_rows_deduped_not_double_counted(self) -> None:
        content = csv_file(
            "BIZ-001,2026-01,100.00,CNY",
            "BIZ-001,2026-01,100.00,CNY",
        )
        self.importer.import_file(filename="a.csv", content=content, source_name="门店A")
        group = self.importer.list_groups()[0]
        self.assertEqual(group["status"], GROUP_CONSISTENT)
        roles = [c["role"] for c in group["candidates"]]
        self.assertIn(CANDIDATE_DUPLICATE, roles)
        self.assertEqual(roles.count(CANDIDATE_ACTIVE), 1)

    def test_duplicate_sources_do_not_accumulate_across_recomputes(self) -> None:
        content = csv_file("BIZ-001,2026-01,100.00,CNY")
        for source in ("门店A", "门店B", "门店C"):
            self.importer.import_file(
                filename=f"{source}.csv", content=content, source_name=source
            )
        group = self.importer.list_groups()[0]
        active = next(c for c in group["candidates"] if c["role"] == CANDIDATE_ACTIVE)
        # 两次跨源重复候选各登记一次，不能因多轮 recompute 而重复累积
        self.assertEqual(len(active["duplicate_sources"]), 2)
        self.assertEqual(
            sorted(item["source_name"] for item in active["duplicate_sources"]),
            ["门店B", "门店C"],
        )

    # ------------------------------------------------------------ 跨源冲突
    def test_cross_source_same_biz_no_conflict_excluded_until_resolved(self) -> None:
        source_a = csv_file("BIZ-001,2026-01,100.00,CNY")
        source_b = csv_file("BIZ-001,2026-01,180.00,CNY")  # 同号异值
        self.importer.import_file(filename="a.csv", content=source_a, source_name="门店A")
        self.importer.import_file(filename="b.csv", content=source_b, source_name="门店B")

        group = self.importer.list_groups(status=GROUP_CONFLICT)[0]
        self.assertEqual(len(group["conflict_candidates"]), 2)
        self.assertFalse(group["included_in_summary"])
        self.assertIn("分歧", group["basis"])
        # 两个候选角色都是冲突候选，行序/导入先后不决定可信度
        self.assertTrue(
            all(c["role"] == CANDIDATE_CONFLICT for c in group["candidates"])
        )

        # 未裁决发布：该组进入未计入冲突项，金额不被累计
        dataset, message = self.importer.publish_dataset()
        self.assertEqual(dataset["record_count"], 0)
        self.assertEqual(dataset["conflict_group_count"], 1)
        self.assertEqual(len(dataset["excluded_conflicts"]), 1)
        self.assertEqual(dataset["summaries"], [])

        # 裁决必须给依据
        _, rejected = self.importer.resolve_conflict(
            group["id"], group["candidates"][0]["candidate_id"], reason="  "
        )
        self.assertIn("依据", rejected)

        chosen = next(
            c for c in group["candidates"] if Decimal(c["amount"]) == Decimal("180.00")
        )
        updated, msg = self.importer.resolve_conflict(
            group["id"],
            chosen["candidate_id"],
            reason="门店B经对账确认，为最终开票金额",
            operator="财务主管",
        )
        self.assertIsNotNone(updated)
        view = self.importer.list_groups(status=GROUP_RESOLVED)[0]
        self.assertTrue(view["included_in_summary"])
        self.assertIn("人工裁决", view["basis"])

        dataset2, _ = self.importer.publish_dataset()
        self.assertEqual(dataset2["record_count"], 1)
        self.assertEqual(Decimal(dataset2["summaries"][0]["amount"]), Decimal("180.00"))
        self.assertEqual(dataset2["conflict_group_count"], 0)

    def test_period_and_currency_conflict_also_detected(self) -> None:
        source_a = csv_file("BIZ-001,2026-01,100.00,CNY")
        source_b = csv_file("BIZ-001,2026-02,100.00,CNY")  # 周期冲突
        source_c = csv_file("BIZ-001,2026-01,100.00,USD")  # 币种冲突
        for name, content, source in [
            ("a.csv", source_a, "门店A"),
            ("b.csv", source_b, "门店B"),
            ("c.csv", source_c, "门店C"),
        ]:
            self.importer.import_file(filename=name, content=content, source_name=source)
        group = self.importer.list_groups(status=GROUP_CONFLICT)[0]
        self.assertEqual(len(group["conflict_candidates"]), 3)

    def test_currency_amounts_never_mixed(self) -> None:
        content = csv_file(
            "BIZ-001,2026-01,100.00,CNY",
            "BIZ-002,2026-01,200.00,CNY",
            "BIZ-003,2026-01,300.00,USD",
            "BIZ-004,2026-02,400.00,USD",
        )
        self.importer.import_file(filename="a.csv", content=content, source_name="门店A")
        dataset, _ = self.importer.publish_dataset()
        summaries = {
            (s["period"], s["currency"]): Decimal(s["amount"]) for s in dataset["summaries"]
        }
        self.assertEqual(summaries[("2026-01", "CNY")], Decimal("300.00"))
        self.assertEqual(summaries[("2026-01", "USD")], Decimal("300.00"))
        self.assertEqual(summaries[("2026-02", "USD")], Decimal("400.00"))
        # 不存在跨币种混合桶
        self.assertNotIn(("2026-01", "CNY+USD"), summaries)

    # ------------------------------------------------------------ 原子性与追溯
    def test_failed_import_leaves_no_half_batch(self) -> None:
        good = csv_file("BIZ-001,2026-01,100.00,CNY")
        self.importer.import_file(filename="good.csv", content=good, source_name="门店A")
        before_files = len(detail_store.source_files)
        before_batches = len(detail_store.import_batches)
        before_groups = len(detail_store.merge_groups)

        with self.assertRaises(FileParseError):
            self.importer.import_file(
                filename="broken.csv", content="不是,合法,表头\nx,y,z\n", source_name="门店A"
            )
        self.assertEqual(len(detail_store.source_files), before_files)
        self.assertEqual(len(detail_store.import_batches), before_batches)
        self.assertEqual(len(detail_store.merge_groups), before_groups)

        # 重试一个正常文件成功，前序数据仍成套可用
        retry = csv_file("BIZ-002,2026-01,50.00,CNY")
        result = self.importer.import_file(
            filename="retry.csv", content=retry, source_name="门店B"
        )
        self.assertFalse(result["deduplicated"])
        dataset, _ = self.importer.publish_dataset()
        self.assertEqual(dataset["record_count"], 2)

    def test_every_published_record_is_traceable(self) -> None:
        content = csv_file(
            "BIZ-001,2026-01,100.00,CNY",
            "BIZ-001,2026-01,100.00,CNY",
        )
        self.importer.import_file(filename="a.csv", content=content, source_name="门店A")
        dataset, _ = self.importer.publish_dataset()
        record = dataset["records"][0]
        self.assertEqual(record["source_name"], "门店A")
        self.assertEqual(record["filename"], "a.csv")
        self.assertEqual(record["line_no"], 2)
        self.assertEqual(len(record["trace"]), 2)  # 组内全部候选都留痕
        self.assertTrue(any(item["role"] == CANDIDATE_DUPLICATE for item in record["trace"]))
        self.assertTrue(all("original_line" in item for item in record["trace"]))
        self.assertIn("去重", record["basis"])

    def test_invalid_rows_listed_with_source_and_line(self) -> None:
        content = csv_file("BIZ-001,2026-01,oops,CNY")
        self.importer.import_file(filename="a.csv", content=content, source_name="门店A")
        rows = self.importer.list_invalid_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "a.csv")
        self.assertEqual(rows[0]["source_name"], "门店A")
        self.assertEqual(rows[0]["line_no"], 2)

    # ------------------------------------------------------------ 版本不可变与报告
    def test_report_snapshot_immutable_after_later_imports(self) -> None:
        first = csv_file(
            "BIZ-001,2026-01,100.00,CNY",
            "BIZ-002,2026-01,200.00,CNY",
        )
        self.importer.import_file(filename="a.csv", content=first, source_name="门店A")
        ds1, _ = self.importer.publish_dataset()

        snapshot, msg = self.reporter.generate_snapshot(report_id=1)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["dataset_version"], ds1["version"])
        self.assertEqual(len(snapshot["source_scope"]), 1)
        first_total = {t["currency"]: Decimal(t["amount"]) for t in snapshot["total_by_currency"]}
        self.assertEqual(first_total["CNY"], Decimal("300.00"))
        self.assertIn("数据版本", snapshot["attachment_content"])
        self.assertIn("门店A/a.csv", snapshot["attachment_content"])

        # 后续再导入并发布新版本
        second = csv_file("BIZ-003,2026-01,500.00,CNY")
        self.importer.import_file(filename="b.csv", content=second, source_name="门店B")
        ds2, _ = self.importer.publish_dataset()
        self.assertNotEqual(ds1["version"], ds2["version"])

        # 历史报告快照内容不变
        stored = self.reporter.get_snapshot(snapshot["snapshot_id"])
        self.assertEqual(stored["record_count"], 2)
        self.assertEqual(stored["dataset_version"], ds1["version"])
        self.assertEqual(len(stored["source_scope"]), 1)
        # 新报告取最新版本
        snapshot2, _ = self.reporter.generate_snapshot(report_id=2)
        self.assertEqual(snapshot2["dataset_version"], ds2["version"])
        self.assertEqual(snapshot2["record_count"], 3)
        self.assertEqual(len(snapshot2["source_scope"]), 2)

    def test_snapshot_records_excluded_conflicts_and_filter(self) -> None:
        self.importer.import_file(
            filename="a.csv",
            content=csv_file("BIZ-001,2026-01,100.00,CNY", "BIZ-002,2026-01,90.00,USD"),
            source_name="门店A",
        )
        self.importer.import_file(
            filename="b.csv",
            content=csv_file("BIZ-001,2026-01,160.00,CNY"),
            source_name="门店B",
        )
        dataset, _ = self.importer.publish_dataset()
        self.assertEqual(dataset["record_count"], 1)
        self.assertEqual(dataset["conflict_group_count"], 1)

        # 仅筛选 CNY 时，唯一的 CNY 业务编号在冲突组里，没有可汇总的已发布明细
        empty_snapshot, empty_message = self.reporter.generate_snapshot(
            report_id=7, currencies=["CNY"]
        )
        self.assertIsNone(empty_snapshot)
        self.assertIn("没有可汇总", empty_message)

        # 全量快照保留未计入冲突项，USD 一致组正常出汇总
        full_snapshot, _ = self.reporter.generate_snapshot(report_id=7)
        self.assertEqual(len(full_snapshot["excluded_conflicts"]), 1)
        self.assertEqual(full_snapshot["excluded_conflicts"][0]["biz_no"], "BIZ-001")
        self.assertEqual(full_snapshot["summaries"][0]["currency"], "USD")

    def test_published_dataset_versions_are_immutable_snapshots(self) -> None:
        self.importer.import_file(
            filename="a.csv",
            content=csv_file("BIZ-001,2026-01,100.00,CNY"),
            source_name="门店A",
        )
        ds1, _ = self.importer.publish_dataset()
        # 另一个来源上报同号同值（文件内容不同，含各自的新增编号），归并时去重不累计
        self.importer.import_file(
            filename="b.csv",
            content=csv_file(
                "BIZ-001,2026-01,100.00,CNY",
                "BIZ-009,2026-01,70.00,CNY",
            ),
            source_name="门店B",
        )
        ds2, _ = self.importer.publish_dataset()
        self.assertEqual(ds1["record_count"], 1)
        self.assertEqual(ds2["record_count"], 2)  # BIZ-001 同值去重，只新增 BIZ-009
        self.assertEqual(ds1["source_scope"][0]["source_name"], "门店A")
        self.assertEqual(len(ds2["source_scope"]), 2)
        # 历史版本的来源范围不被后续导入改写
        self.assertEqual(len(ds1["source_scope"]), 1)


if __name__ == "__main__":
    unittest.main()
