"""多源经营明细导入、校验、去重与归并的业务规则。

设计要点（对应需求口径）：

1. 每次上传保留原始文件与内容指纹；相同来源内容重复导入只登记一次，
   经营金额不会被累计两次。
2. 无效金额、缺业务编号或周期的行进无效行清单，带原始文件名与行号，
   绝不当作零值参与汇总。
3. 同一业务编号跨来源出现时按编号归并成一组：值完全一致的候选只去重不累计；
   金额、周期、币种有分歧的组标记为冲突，整组默认不参与汇总，
   既不静默覆盖，也不重复累计。
4. 源文件行序与导入先后不代表可信度：组内候选按稳定口径排序展示，
   冲突必须人工裁决，裁决依据完整留痕。
5. 发布生成不可变数据集快照；已发布明细与来源依据成套保存。
   后续导入/裁决只产生新版本，不改写历史版本与报告。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.detail_store import DetailStore, detail_store
from app.services.detail_parser import FileParseError, parse_detail_file

# 归并分组状态
GROUP_CONSISTENT = "一致"      # 全部候选去重后口径一致，可参与汇总
GROUP_CONFLICT = "冲突"        # 候选之间存在分歧，默认不参与汇总
GROUP_RESOLVED = "已裁决"      # 冲突已人工裁决，按裁决结果参与汇总

# 候选在组内的角色
CANDIDATE_DUPLICATE = "重复"   # 与被保留候选完全一致，去重不参与
CANDIDATE_ACTIVE = "入选"      # 去重/裁决后代表该业务编号的候选
CANDIDATE_CONFLICT = "冲突候选"
CANDIDATE_EXCLUDED = "排除"    # 裁决时被弃用的冲突候选


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _decimal_to_str(value: Decimal) -> str:
    """Decimal 统一转字符串输出，避免浮点误差与 JSON 数字精度问题。"""
    normalized = value.normalize()
    if normalized == Decimal(0):
        return "0"
    return format(normalized, "f")


class DetailImportService:
    def __init__(self, store: DetailStore | None = None) -> None:
        self.store = store or detail_store

    # ------------------------------------------------------------------ 上传导入
    def import_file(
        self,
        *,
        filename: str,
        content: str,
        source_name: str,
        datasource_id: int | None = None,
    ) -> dict[str, Any]:
        """导入一个本地明细文件，全流程在一次调用内完成（失败不留半批）。

        返回批次摘要。重复文件走幂等分支：直接回传原批次，不新增任何明细。
        """
        name = (filename or "").strip()
        source = (source_name or "").strip()
        if not name:
            raise FileParseError("文件名不能为空")
        if not source:
            raise FileParseError("数据源名称不能为空")

        # 解析与逐行校验先在内存完成，任何一步抛错都不会写入仓库
        parsed = parse_detail_file(content)
        fingerprint = _fingerprint(content)

        # 相同来源重复导入同一内容按幂等处理；不同来源的同内容文件仍登记来源依据，
        # 是否累计由归并层按业务口径去重决定，不会把金额算两次
        existing_batch = self.store.find_batch_by_fingerprint(fingerprint, source)
        if existing_batch is not None:
            return {
                "deduplicated": True,
                "batch": existing_batch,
                "message": (
                    f"数据源 {source} 已导入过相同内容的文件（{existing_batch['filename']}），"
                    "本次按重复文件处理，未新增经营金额"
                ),
            }

        source_file = {
            "id": self.store.next_id("file"),
            "filename": name,
            "source_name": source,
            "datasource_id": datasource_id,
            "fingerprint": fingerprint,
            "size": len(content.encode("utf-8")),
            "uploaded_at": _now(),
            # 原始内容成套保留，供追溯与复核
            "raw_content": content,
        }
        self.store.source_files.append(source_file)

        batch = {
            "id": self.store.next_id("batch"),
            "file_id": source_file["id"],
            "filename": name,
            "source_name": source,
            "datasource_id": datasource_id,
            "fingerprint": fingerprint,
            "imported_at": _now(),
            "status": "已导入",
            "valid_count": len(parsed["valid_rows"]),
            "invalid_count": len(parsed["invalid_rows"]),
            "data_row_count": parsed["data_row_count"],
            "invalid_rows": [
                {
                    "file_id": source_file["id"],
                    "filename": name,
                    "source_name": source,
                    **row,
                }
                for row in parsed["invalid_rows"]
            ],
        }
        self.store.import_batches.append(batch)

        # 有效候选写入归并分组；无效行进批次台账，不进入分组、不按零处理
        for row in parsed["valid_rows"]:
            self._upsert_candidate(source_file, batch, row)

        self._recompute_groups()
        return {
            "deduplicated": False,
            "batch": batch,
            "message": (
                f"文件 {name} 导入完成：有效 {batch['valid_count']} 行，"
                f"无效 {batch['invalid_count']} 行（无效行可在批次台账定位原始行）"
            ),
        }

    def _upsert_candidate(
        self,
        source_file: dict[str, Any],
        batch: dict[str, Any],
        row: dict[str, Any],
    ) -> None:
        """把一行有效明细作为候选写入对应业务编号的归并组。"""
        group = self.store.find_group_by_biz_no(row["biz_no"])
        if group is None:
            group = {
                "id": self.store.next_id("group"),
                "biz_no": row["biz_no"],
                "status": GROUP_CONSISTENT,
                "candidates": [],
                "resolution": None,
                # 已发布版本号；发布后该组在新草稿区被修改前用于判断是否有新变化
                "last_published_version": None,
            }
            self.store.merge_groups.append(group)

        # 同一文件同一物理行重复出现也视为同一条候选（文件内重复行）
        for candidate in group["candidates"]:
            if (
                candidate["file_id"] == source_file["id"]
                and candidate["line_no"] == row["line_no"]
            ):
                return

        group["candidates"].append({
            "candidate_id": self.store.next_id("candidate"),
            "biz_no": row["biz_no"],
            "period": row["period"],
            "currency": row["currency"],
            "amount": row["amount"],
            "amount_text": _decimal_to_str(row["amount"]),
            "file_id": source_file["id"],
            "batch_id": batch["id"],
            "filename": source_file["filename"],
            "source_name": source_file["source_name"],
            "line_no": row["line_no"],
            "original_line": row["original_line"],
            "imported_at": batch["imported_at"],
            "role": CANDIDATE_ACTIVE,
        })
        # 新候选进入后，原裁决依据可能失效，交由 recompute 统一判定
        group["resolution"] = None

    def _recompute_groups(self) -> None:
        """重新计算每个归并组的去重结果、冲突状态与候选角色。

        排序不使用行序/导入先后作为可信度，只用业务编号、来源名、文件名、行号
        做稳定展示排序；是否入选完全取决于数据本身与人工裁决。
        """
        for group in self.store.merge_groups:
            # 每次重算先清掉上一轮的去重标记，避免重复 append 造成台账膨胀
            for candidate in group["candidates"]:
                candidate.pop("duplicate_of", None)
                candidate.pop("duplicate_sources", None)

            candidates = sorted(
                group["candidates"],
                key=lambda item: (
                    item["source_name"],
                    item["filename"],
                    item["line_no"],
                    item["candidate_id"],
                ),
            )
            # 按业务口径（周期/币种/金额）去重
            unique_by_signature: list[dict[str, Any]] = []
            signatures: dict[tuple[str, str, str], dict[str, Any]] = {}
            for candidate in candidates:
                signature = (
                    candidate["period"],
                    candidate["currency"],
                    candidate["amount_text"],
                )
                kept = signatures.get(signature)
                if kept is None:
                    signatures[signature] = candidate
                    unique_by_signature.append(candidate)
                    candidate["role"] = CANDIDATE_ACTIVE
                else:
                    candidate["role"] = CANDIDATE_DUPLICATE
                    candidate["duplicate_of"] = kept["candidate_id"]
                    kept.setdefault("duplicate_sources", []).append({
                        "candidate_id": candidate["candidate_id"],
                        "source_name": candidate["source_name"],
                        "filename": candidate["filename"],
                        "line_no": candidate["line_no"],
                    })

            conflicting = len(unique_by_signature) > 1
            if conflicting:
                if group["resolution"] is not None:
                    self._apply_resolution_roles(group)
                else:
                    group["status"] = GROUP_CONFLICT
                    for candidate in unique_by_signature:
                        candidate["role"] = CANDIDATE_CONFLICT
            else:
                group["status"] = GROUP_CONSISTENT
                group["resolution"] = None
                for candidate in unique_by_signature:
                    candidate["role"] = CANDIDATE_ACTIVE

    # ------------------------------------------------------------------ 冲突裁决
    def resolve_conflict(
        self,
        group_id: int,
        candidate_id: int,
        *,
        reason: str,
        operator: str = "分析员",
    ) -> tuple[dict[str, Any] | None, str]:
        """人工裁决冲突组：指定一个候选作为该业务编号的最终口径。"""
        group = self.store.get_group(group_id)
        if group is None:
            return None, f"归并分组 {group_id} 不存在"
        chosen = next(
            (item for item in group["candidates"] if item["candidate_id"] == candidate_id),
            None,
        )
        if chosen is None:
            return None, f"候选 {candidate_id} 不属于业务编号 {group['biz_no']} 的归并组"
        if not reason or not reason.strip():
            return None, "裁决必须填写依据，不能无理由覆盖有分歧的数据"

        group["resolution"] = {
            "chosen_candidate_id": candidate_id,
            "reason": reason.strip(),
            "operator": operator,
            "decided_at": _now(),
        }
        self._apply_resolution_roles(group)
        return group, f"业务编号 {group['biz_no']} 已按候选 {candidate_id} 裁决"

    def _apply_resolution_roles(self, group: dict[str, Any]) -> None:
        resolution = group["resolution"]
        chosen_id = resolution["chosen_candidate_id"]
        for candidate in group["candidates"]:
            if candidate["role"] == CANDIDATE_DUPLICATE:
                continue
            if candidate["candidate_id"] == chosen_id:
                candidate["role"] = CANDIDATE_ACTIVE
            else:
                candidate["role"] = CANDIDATE_EXCLUDED
        group["status"] = GROUP_RESOLVED

    # ------------------------------------------------------------------ 查询视图
    def list_batches(self) -> list[dict[str, Any]]:
        return self.store.import_batches

    def get_batch_detail(self, batch_id: int) -> dict[str, Any] | None:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            return None
        file = self.store.get_file(batch["file_id"])
        return {
            "batch": batch,
            "source_file": {
                key: value for key, value in (file or {}).items() if key != "raw_content"
            },
            "raw_content": file.get("raw_content") if file else None,
        }

    def list_invalid_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for batch in self.store.import_batches:
            rows.extend(batch["invalid_rows"])
        return rows

    def list_groups(self, status: str | None = None) -> list[dict[str, Any]]:
        groups = self.store.merge_groups
        if status:
            groups = [group for group in groups if group["status"] == status]
        return [self._group_view(group) for group in groups]

    def _group_view(self, group: dict[str, Any]) -> dict[str, Any]:
        active = [c for c in group["candidates"] if c["role"] == CANDIDATE_ACTIVE]
        included = group["status"] in (GROUP_CONSISTENT, GROUP_RESOLVED) and bool(active)
        basis = self._inclusion_basis(group, active, included)
        return {
            "id": group["id"],
            "biz_no": group["biz_no"],
            "status": group["status"],
            "included_in_summary": included,
            "basis": basis,
            "resolution": group["resolution"],
            "candidate_count": len(group["candidates"]),
            "conflict_candidates": [
                self._candidate_view(item)
                for item in group["candidates"]
                if item["role"] in (CANDIDATE_CONFLICT, CANDIDATE_EXCLUDED)
            ],
            "candidates": [self._candidate_view(item) for item in group["candidates"]],
            "active_candidate": self._candidate_view(active[0]) if active else None,
        }

    def _inclusion_basis(
        self,
        group: dict[str, Any],
        active: list[dict[str, Any]],
        included: bool,
    ) -> str:
        if group["status"] == GROUP_CONSISTENT:
            dupes = sum(1 for c in group["candidates"] if c["role"] == CANDIDATE_DUPLICATE)
            extra = f"，另有 {dupes} 条重复候选已去重" if dupes else ""
            return f"全部来源口径一致，去重后保留 1 条入选候选{extra}"
        if group["status"] == GROUP_CONFLICT:
            return "跨来源同号数据存在金额/周期/币种分歧，未裁决前整组不参与汇总，避免静默覆盖或重复累计"
        if group["status"] == GROUP_RESOLVED and active:
            resolution = group["resolution"]
            return (
                f"人工裁决入选候选 {active[0]['candidate_id']}"
                f"（{active[0]['source_name']} {active[0]['filename']}:{active[0]['line_no']}），"
                f"依据：{resolution['reason']}（{resolution['operator']} {resolution['decided_at']}）"
            )
        return "暂无入选候选，不参与汇总"

    def _candidate_view(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": candidate["candidate_id"],
            "biz_no": candidate["biz_no"],
            "period": candidate["period"],
            "currency": candidate["currency"],
            "amount": candidate["amount_text"],
            "source_name": candidate["source_name"],
            "filename": candidate["filename"],
            "file_id": candidate["file_id"],
            "line_no": candidate["line_no"],
            "original_line": candidate["original_line"],
            "imported_at": candidate["imported_at"],
            "role": candidate["role"],
            "duplicate_of": candidate.get("duplicate_of"),
            "duplicate_sources": candidate.get("duplicate_sources", []),
        }

    # ------------------------------------------------------------------ 发布数据集
    def publish_dataset(self, remark: str | None = None) -> tuple[dict[str, Any] | None, str]:
        """把当前草稿区归并结果固化成不可变数据集版本。

        冲突未裁决的组不纳入版本明细，只登记为未计入冲突项；
        快照同时拷贝来源依据，保证已发布明细与依据成套可用。
        """
        if not self.store.merge_groups:
            return None, "暂无可发布的经营明细，请先导入明细文件"

        version = f"DS-{len(self.store.datasets) + 1:04d}"
        published_records: list[dict[str, Any]] = []
        excluded_conflicts: list[dict[str, Any]] = []
        consistent = resolved = conflict = 0

        for group in self.store.merge_groups:
            view = self._group_view(group)
            if view["included_in_summary"] and view["active_candidate"]:
                chosen = view["active_candidate"]
                published_records.append({
                    "biz_no": group["biz_no"],
                    "period": chosen["period"],
                    "currency": chosen["currency"],
                    "amount": chosen["amount"],
                    "group_id": group["id"],
                    "group_status": group["status"],
                    "basis": view["basis"],
                    "candidate_id": chosen["candidate_id"],
                    "source_name": chosen["source_name"],
                    "filename": chosen["filename"],
                    "line_no": chosen["line_no"],
                    "trace": self._trace_of(group, chosen["candidate_id"]),
                })
                if group["status"] == GROUP_RESOLVED:
                    resolved += 1
                else:
                    consistent += 1
            else:
                conflict += 1
                excluded_conflicts.append({
                    "group_id": group["id"],
                    "biz_no": group["biz_no"],
                    "status": group["status"],
                    "basis": view["basis"],
                    "candidates": view["candidates"],
                })

        # 来源范围：全部已导入来源文件成套登记，冲突候选引用到的文件也包含在内
        source_scope = [
            {
                "file_id": file["id"],
                "filename": file["filename"],
                "source_name": file["source_name"],
                "fingerprint": file["fingerprint"],
                "uploaded_at": file["uploaded_at"],
            }
            for file in self.store.source_files
        ]

        summaries = self._summarize(published_records)
        dataset = {
            "version": version,
            "published_at": _now(),
            "remark": remark,
            "status": "已发布",
            "record_count": len(published_records),
            "conflict_group_count": conflict,
            "consistent_group_count": consistent,
            "resolved_group_count": resolved,
            "records": published_records,
            "excluded_conflicts": excluded_conflicts,
            "source_scope": source_scope,
            "batch_ids": [batch["id"] for batch in self.store.import_batches],
            "summaries": summaries,
        }
        self.store.datasets.append(dataset)
        for group in self.store.merge_groups:
            group["last_published_version"] = version
        return dataset, f"数据集 {version} 已发布：纳入 {len(published_records)} 条明细，{conflict} 个冲突组未计入"

    def _trace_of(self, group: dict[str, Any], chosen_candidate_id: int) -> list[dict[str, Any]]:
        """一条已发布明细的完整追溯链：组内全部候选 + 各自来源与原始行。"""
        trace = []
        for candidate in group["candidates"]:
            trace.append({
                "candidate_id": candidate["candidate_id"],
                "source_name": candidate["source_name"],
                "filename": candidate["filename"],
                "file_id": candidate["file_id"],
                "line_no": candidate["line_no"],
                "original_line": candidate["original_line"],
                "period": candidate["period"],
                "currency": candidate["currency"],
                "amount": candidate["amount_text"],
                "role": candidate["role"],
                "chosen": candidate["candidate_id"] == chosen_candidate_id,
            })
        return trace

    def _summarize(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按周期 + 币种汇总金额；币种不一致绝不混加。"""
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

    def list_datasets(self) -> list[dict[str, Any]]:
        # 列表不回传大字段，明细走详情接口
        return [
            {
                key: value
                for key, value in dataset.items()
                if key not in ("records", "excluded_conflicts")
            }
            for dataset in self.store.datasets
        ]

    def get_dataset(self, version: str) -> dict[str, Any] | None:
        return self.store.get_dataset(version)
