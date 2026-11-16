"""经营明细领域的内存数据仓库。

与通用的 ``app.store`` 分开：经营明细的导入、归并、发布要保留批次/来源/原始行等
成套依据，结构比通用模块行复杂，后续真实项目里这里会换成带事务的数据库访问层。

所有写操作只在本模块内发生，service 层负责业务规则，保证发布出去的数据版本
不可变，后续导入或冲突处理只能影响下一个版本。
"""
from __future__ import annotations

from typing import Any


class DetailStore:
    def __init__(self) -> None:
        # 上传过的原始文件：按内容指纹去重
        self.source_files: list[dict[str, Any]] = []
        # 导入批次：每次上传解析生成一条，重复文件复用同一批次
        self.import_batches: list[dict[str, Any]] = []
        # 归并分组：按业务编号聚合的候选明细，草稿区与已发布快照分开
        self.merge_groups: list[dict[str, Any]] = []
        # 已发布的经营明细数据集（不可变快照）
        self.datasets: list[dict[str, Any]] = []
        # 经营分析报告生成的取数快照（不可变）
        self.report_snapshots: list[dict[str, Any]] = []
        # 自增序号
        self._seq: dict[str, int] = {}

    def next_id(self, key: str) -> int:
        self._seq[key] = self._seq.get(key, 0) + 1
        return self._seq[key]

    def find_file(self, fingerprint: str) -> dict[str, Any] | None:
        for item in self.source_files:
            if item["fingerprint"] == fingerprint:
                return item
        return None

    def find_batch_by_fingerprint(
        self, fingerprint: str, source_name: str | None = None
    ) -> dict[str, Any] | None:
        for item in self.import_batches:
            if item["fingerprint"] != fingerprint:
                continue
            if source_name is None or item["source_name"] == source_name:
                return item
        return None

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        for item in self.import_batches:
            if int(item["id"]) == batch_id:
                return item
        return None

    def get_file(self, file_id: int) -> dict[str, Any] | None:
        for item in self.source_files:
            if int(item["id"]) == file_id:
                return item
        return None

    def get_group(self, group_id: int) -> dict[str, Any] | None:
        for item in self.merge_groups:
            if int(item["id"]) == group_id:
                return item
        return None

    def find_group_by_biz_no(self, biz_no: str) -> dict[str, Any] | None:
        for item in self.merge_groups:
            if item["biz_no"] == biz_no:
                return item
        return None

    def get_dataset(self, version: str) -> dict[str, Any] | None:
        for item in self.datasets:
            if item["version"] == version:
                return item
        return None

    def latest_dataset(self) -> dict[str, Any] | None:
        return self.datasets[-1] if self.datasets else None

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        for item in self.report_snapshots:
            if item["snapshot_id"] == snapshot_id:
                return item
        return None

    def reset(self) -> None:
        """测试辅助：清空全部经营明细数据。"""
        self.source_files.clear()
        self.import_batches.clear()
        self.merge_groups.clear()
        self.datasets.clear()
        self.report_snapshots.clear()
        self._seq.clear()


detail_store = DetailStore()
