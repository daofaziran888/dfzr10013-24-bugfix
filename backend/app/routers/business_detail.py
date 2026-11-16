"""经营明细导入接口：多源明细上传、校验台账、冲突归并、数据集发布与报告取数。

路由层只做参数解析与 HTTP 状态映射，业务判断全部在 service 层。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ConflictResolvePayload,
    DatasetPublishPayload,
    DetailFilePayload,
    ReportSnapshotPayload,
)
from app.services.detail_import import DetailImportService
from app.services.detail_parser import FileParseError
from app.services.report_snapshot import ReportSnapshotService

router = APIRouter(prefix="/api/business-detail", tags=["经营明细导入"])

import_service = DetailImportService()
snapshot_service = ReportSnapshotService()


# ---------------------------------------------------------------- 导入与批次
@router.post("/imports")
def import_detail_file(payload: DetailFilePayload) -> dict:
    """上传并导入一个数据源的本地明细文件；重复文件幂等，不新增经营金额。"""
    try:
        result = import_service.import_file(
            filename=payload.filename,
            content=payload.content,
            source_name=payload.source_name,
            datasource_id=payload.datasource_id,
        )
    except FileParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "deduplicated": result["deduplicated"],
        "message": result["message"],
        "batch": result["batch"],
    }


@router.get("/imports")
def list_imports() -> dict:
    """导入批次台账：每个文件的有效/无效行数与处理状态。"""
    batches = import_service.list_batches()
    return {"items": batches, "total": len(batches)}


@router.get("/imports/{batch_id}")
def get_import(batch_id: int) -> dict:
    """批次详情：含原始文件内容与无效行定位信息。"""
    detail = import_service.get_batch_detail(batch_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"导入批次 {batch_id} 不存在")
    return detail


@router.get("/invalid-rows")
def list_invalid_rows() -> dict:
    """全部无效行台账：带数据源、文件名与原始行号，绝不按零值处理。"""
    rows = import_service.list_invalid_rows()
    return {"items": rows, "total": len(rows)}


# ---------------------------------------------------------------- 归并与冲突
@router.get("/groups")
def list_groups(
    status: str | None = Query(default=None, description="一致、冲突、已裁决"),
) -> dict:
    """归并分组：列出冲突候选、是否参与汇总及依据。"""
    groups = import_service.list_groups(status=status)
    return {"items": groups, "total": len(groups)}


@router.get("/groups/{group_id}")
def get_group(group_id: int) -> dict:
    groups = {group["id"]: group for group in import_service.list_groups()}
    group = groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"归并分组 {group_id} 不存在")
    return group


@router.post("/groups/{group_id}/resolution")
def resolve_conflict(group_id: int, payload: ConflictResolvePayload) -> dict:
    """人工裁决冲突组：指定入选候选并留痕裁决依据。"""
    group, message = import_service.resolve_conflict(
        group_id,
        payload.candidate_id,
        reason=payload.reason,
        operator=payload.operator,
    )
    if group is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "group": _find_group(group_id)}


def _find_group(group_id: int) -> dict:
    for group in import_service.list_groups():
        if group["id"] == group_id:
            return group
    raise HTTPException(status_code=404, detail=f"归并分组 {group_id} 不存在")


# ---------------------------------------------------------------- 数据集发布
@router.post("/datasets/publish")
def publish_dataset(payload: DatasetPublishPayload) -> dict:
    """把当前归并结果固化为不可变数据集版本，冲突组计入未计项而非静默丢弃。"""
    dataset, message = import_service.publish_dataset(payload.remark)
    if dataset is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "dataset": _dataset_view(dataset)}


@router.get("/datasets")
def list_datasets() -> dict:
    items = import_service.list_datasets()
    return {"items": items, "total": len(items)}


@router.get("/datasets/{version}")
def get_dataset(version: str) -> dict:
    dataset = import_service.get_dataset(version)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"数据集版本 {version} 不存在")
    return _dataset_view(dataset)


# ---------------------------------------------------------------- 报告取数快照
@router.post("/report-snapshots")
def generate_report_snapshot(payload: ReportSnapshotPayload) -> dict:
    """经营分析报告从已发布数据集按周期/币种汇总，固化版本、来源与未计冲突项。"""
    snapshot, message = snapshot_service.generate_snapshot(
        payload.report_id,
        version=payload.version,
        periods=payload.periods,
        currencies=payload.currencies,
    )
    if snapshot is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "snapshot": _snapshot_view(snapshot, include_attachment=False)}


@router.get("/report-snapshots")
def list_report_snapshots(
    report_id: int | None = Query(default=None, description="按经营分析报告 id 过滤"),
) -> dict:
    items = snapshot_service.list_snapshots(report_id)
    return {"items": items, "total": len(items)}


@router.get("/report-snapshots/{snapshot_id}")
def get_report_snapshot(snapshot_id: str) -> dict:
    snapshot = snapshot_service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"报告快照 {snapshot_id} 不存在")
    return _snapshot_view(snapshot, include_attachment=False)


@router.get("/report-snapshots/{snapshot_id}/attachment")
def download_attachment(snapshot_id: str) -> dict:
    """金额汇总附件：内容与快照同批数据，抬头标注数据版本与来源范围。"""
    snapshot = snapshot_service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"报告快照 {snapshot_id} 不存在")
    return {
        "filename": snapshot["attachment_filename"],
        "content_type": "text/csv; charset=utf-8",
        "content": snapshot["attachment_content"],
    }


# ---------------------------------------------------------------- 序列化辅助
def _dataset_view(dataset: dict) -> dict:
    return dict(dataset)


def _snapshot_view(snapshot: dict, *, include_attachment: bool) -> dict:
    view = dict(snapshot)
    if not include_attachment:
        view.pop("attachment_content", None)
    return view
