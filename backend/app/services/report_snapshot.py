"""经营分析报告取数与金额汇总附件。

报告只能从已发布的经营明细数据集取数，生成时把数据版本、来源范围、未计入冲突项
和按周期/币种的金额汇总固化成不可变快照，并产出一份与快照同批数据对应的
CSV 金额汇总附件。后续导入或冲突处理产生的新版本不会改写历史报告。
"""
from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from app.detail_store import detail_store
from app.services.detail_import import _decimal_to_str, _now


class ReportSnapshotService:
    def __init__(self) -> None:
        self.store = detail_store

    def generate_snapshot(
        self,
        report_id: int,
        *,
        version: str | None = None,
        periods: list[str] | None = None,
        currencies: list[str] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        dataset = self.store.latest_dataset() if not version else self.store.get_dataset(version)
        if dataset is None:
            return None, "还没有已发布的经营明细数据集，请先在数据接入模块导入并发布"

        period_filter = {item.strip() for item in (periods or []) if item.strip()}
        currency_filter = {item.strip().upper() for item in (currencies or []) if item.strip()}

        records = [
            record
            for record in dataset["records"]
            if (not period_filter or record["period"] in period_filter)
            and (not currency_filter or record["currency"] in currency_filter)
        ]
        if not records:
            return None, "所选周期与币种在该数据版本中没有可汇总的已发布明细"

        summaries = self._summarize(records)
        # 未计入冲突项按筛选条件同步收敛，但保留完整候选依据
        excluded = [
            conflict
            for conflict in dataset["excluded_conflicts"]
            if (
                not period_filter
                or any(c["period"] in period_filter for c in conflict["candidates"])
            )
        ]
        total_by_currency = self._total_by_currency(summaries)

        snapshot_id = f"RPT-{report_id}-{dataset['version']}-{len(self.store.report_snapshots) + 1:03d}"
        snapshot = {
            "snapshot_id": snapshot_id,
            "report_id": report_id,
            "created_at": _now(),
            "dataset_version": dataset["version"],
            "published_at": dataset["published_at"],
            "period_filter": sorted(period_filter),
            "currency_filter": sorted(currency_filter),
            "source_scope": [dict(item) for item in dataset["source_scope"]],
            "batch_ids": list(dataset["batch_ids"]),
            "record_count": len(records),
            "summaries": summaries,
            "total_by_currency": total_by_currency,
            "excluded_conflicts": [dict(item) for item in excluded],
            "excluded_conflict_count": len(excluded),
            "records": [dict(record) for record in records],
            "attachment_filename": f"{snapshot_id}-金额汇总附件.csv",
        }
        snapshot["attachment_content"] = self._build_attachment_csv(snapshot)
        self.store.report_snapshots.append(snapshot)
        return snapshot, f"报告 {report_id} 已基于数据集 {dataset['version']} 生成金额汇总（{snapshot_id}）"

    def _summarize(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, str], Decimal] = {}
        counts: dict[tuple[str, str], int] = {}
        for record in records:
            key = (record["period"], record["currency"])
            buckets[key] = buckets.get(key, Decimal("0")) + Decimal(record["amount"])
            counts[key] = counts.get(key, 0) + 1
        return [
            {
                "period": period,
                "currency": currency,
                "amount": _decimal_to_str(amount),
                "record_count": counts[(period, currency)],
            }
            for (period, currency), amount in sorted(buckets.items())
        ]

    def _total_by_currency(self, summaries: list[dict[str, Any]]) -> list[dict[str, str]]:
        totals: dict[str, Decimal] = {}
        for item in summaries:
            totals[item["currency"]] = totals.get(item["currency"], Decimal("0")) + Decimal(item["amount"])
        return [
            {"currency": currency, "amount": _decimal_to_str(amount)}
            for currency, amount in sorted(totals.items())
        ]

    def _build_attachment_csv(self, snapshot: dict[str, Any]) -> str:
        """金额汇总附件：抬头写明数据版本与来源范围，保证附件与报告依据同批数据。"""
        buffer = io.StringIO()
        buffer.write(f"# 报告取数快照,{snapshot['snapshot_id']}\n")
        buffer.write(f"# 数据版本,{snapshot['dataset_version']}（发布于 {snapshot['published_at']}）\n")
        scope = "；".join(
            f"{item['source_name']}/{item['filename']}" for item in snapshot["source_scope"]
        )
        buffer.write(f"# 来源范围,{scope}\n")
        if snapshot["period_filter"]:
            buffer.write(f"# 周期筛选,{'、'.join(snapshot['period_filter'])}\n")
        if snapshot["currency_filter"]:
            buffer.write(f"# 币种筛选,{'、'.join(snapshot['currency_filter'])}\n")
        buffer.write(f"# 未计入冲突组数,{len(snapshot['excluded_conflicts'])}\n")
        buffer.write("所属周期,币种,汇总金额,明细条数\n")
        for item in snapshot["summaries"]:
            buffer.write(
                f"{item['period']},{item['currency']},{item['amount']},{item['record_count']}\n"
            )
        buffer.write("币种合计,币种,合计金额\n")
        for item in snapshot["total_by_currency"]:
            buffer.write(f"合计,{item['currency']},{item['amount']}\n")
        return buffer.getvalue()

    def list_snapshots(self, report_id: int | None = None) -> list[dict[str, Any]]:
        items = self.store.report_snapshots
        if report_id is not None:
            items = [item for item in items if int(item["report_id"]) == report_id]
        return [self._list_view(item) for item in items]

    def _list_view(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in snapshot.items()
            if key not in ("attachment_content", "records", "excluded_conflicts")
        }

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return self.store.get_snapshot(snapshot_id)
