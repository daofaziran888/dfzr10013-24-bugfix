"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class DetailFilePayload(BaseModel):
    """经营明细文件导入：文件内容随请求体提交（本地文件由前端读取后上传）。"""

    filename: str
    source_name: str
    content: str
    datasource_id: int | None = None


class ConflictResolvePayload(BaseModel):
    """冲突归并组的人工裁决：必须指定入选候选并写明依据。"""

    candidate_id: int
    reason: str
    operator: str = "分析员"


class DatasetPublishPayload(BaseModel):
    """发布经营明细数据集时的备注。"""

    remark: str | None = None


class ReportSnapshotPayload(BaseModel):
    """经营分析报告取数：指定数据版本与周期/币种筛选，留空取最新版本全量。"""

    report_id: int
    version: str | None = None
    periods: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)



class KpiEntry(BaseModel):
    """经营指标明细结构。"""

    field_0: str | None = None  # 指标编号
    field_1: str | None = None  # 指标名称
    field_2: str | None = None  # 计算公式
    field_3: str | None = None  # 目标值
    field_4: str | None = None  # 当前值
    field_5: str | None = None  # 达成率
    field_6: str | None = None  # 环比变化
    field_7: str | None = None  # 指标状态

class FinanceEntry(BaseModel):
    """财务科目明细结构。"""

    field_0: str | None = None  # 科目编号
    field_1: str | None = None  # 科目名称
    field_2: str | None = None  # 科目类型
    field_3: str | None = None  # 预算金额
    field_4: str | None = None  # 实际金额
    field_5: str | None = None  # 差异比例
    field_6: str | None = None  # 分析周期
    field_7: str | None = None  # 科目状态

class SalesEntry(BaseModel):
    """漏斗阶段明细结构。"""

    field_0: str | None = None  # 阶段编号
    field_1: str | None = None  # 阶段名称
    field_2: str | None = None  # 客户数量
    field_3: str | None = None  # 预计金额
    field_4: str | None = None  # 转化率
    field_5: str | None = None  # 平均周期
    field_6: str | None = None  # 流失原因
    field_7: str | None = None  # 阶段状态

class CustomerEntry(BaseModel):
    """客户画像明细结构。"""

    field_0: str | None = None  # 画像编号
    field_1: str | None = None  # 客户名称
    field_2: str | None = None  # 行业分类
    field_3: str | None = None  # 购买频次
    field_4: str | None = None  # 客单价
    field_5: str | None = None  # 偏好标签
    field_6: str | None = None  # 生命周期
    field_7: str | None = None  # 画像状态

class SupplyEntry(BaseModel):
    """效率指标明细结构。"""

    field_0: str | None = None  # 指标编号
    field_1: str | None = None  # 环节名称
    field_2: str | None = None  # 当前耗时
    field_3: str | None = None  # 标准耗时
    field_4: str | None = None  # 效率得分
    field_5: str | None = None  # 瓶颈识别
    field_6: str | None = None  # 优化建议
    field_7: str | None = None  # 指标状态

class HrEntry(BaseModel):
    """效能数据明细结构。"""

    field_0: str | None = None  # 数据编号
    field_1: str | None = None  # 部门名称
    field_2: str | None = None  # 人效指标
    field_3: str | None = None  # 当前值
    field_4: str | None = None  # 行业均值
    field_5: str | None = None  # 偏差分析
    field_6: str | None = None  # 评估周期
    field_7: str | None = None  # 数据状态

class ForecastEntry(BaseModel):
    """预测任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 预测对象
    field_2: str | None = None  # 预测周期
    field_3: str | None = None  # 预测算法
    field_4: str | None = None  # 预测结果
    field_5: str | None = None  # 置信区间
    field_6: str | None = None  # 实际对比
    field_7: str | None = None  # 任务状态

class AlertEntry(BaseModel):
    """预警记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 预警类型
    field_2: str | None = None  # 预警级别
    field_3: str | None = None  # 触发条件
    field_4: str | None = None  # 影响范围
    field_5: str | None = None  # 建议措施
    field_6: str | None = None  # 发送渠道
    field_7: str | None = None  # 处理状态

class DecisionEntry(BaseModel):
    """决策建议明细结构。"""

    field_0: str | None = None  # 建议编号
    field_1: str | None = None  # 分析主题
    field_2: str | None = None  # 决策选项
    field_3: str | None = None  # 收益评估
    field_4: str | None = None  # 风险评估
    field_5: str | None = None  # 推荐方案
    field_6: str | None = None  # 生成时间
    field_7: str | None = None  # 建议状态

class DrillEntry(BaseModel):
    """下钻路径明细结构。"""

    field_0: str | None = None  # 路径编号
    field_1: str | None = None  # 起点指标
    field_2: str | None = None  # 下钻维度
    field_3: str | None = None  # 下钻层级
    field_4: str | None = None  # 筛选条件
    field_5: str | None = None  # 结果展示
    field_6: str | None = None  # 分析时间
    field_7: str | None = None  # 路径状态

class ReportEntry(BaseModel):
    """分析报告明细结构。"""

    field_0: str | None = None  # 报告编号
    field_1: str | None = None  # 报告主题
    field_2: str | None = None  # 分析周期
    field_3: str | None = None  # 报告模板
    field_4: str | None = None  # 关键发现
    field_5: str | None = None  # 数据附件
    field_6: str | None = None  # 分发对象
    field_7: str | None = None  # 报告状态

class CompareEntry(BaseModel):
    """对比方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 对比指标
    field_2: str | None = None  # 基准周期
    field_3: str | None = None  # 对比周期
    field_4: str | None = None  # 变化幅度
    field_5: str | None = None  # 变化方向
    field_6: str | None = None  # 原因分析
    field_7: str | None = None  # 方案状态

class DatasourceEntry(BaseModel):
    """接入配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 数据源名称
    field_2: str | None = None  # 连接字符串
    field_3: str | None = None  # 认证方式
    field_4: str | None = None  # 默认库表
    field_5: str | None = None  # 刷新频率
    field_6: str | None = None  # 最后同步
    field_7: str | None = None  # 配置状态

class CacheEntry(BaseModel):
    """缓存策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 缓存对象
    field_2: str | None = None  # 缓存时间
    field_3: str | None = None  # 失效条件
    field_4: str | None = None  # 预加载
    field_5: str | None = None  # 容量上限
    field_6: str | None = None  # 命中统计
    field_7: str | None = None  # 策略状态

class TemplateEntry(BaseModel):
    """分析模板明细结构。"""

    field_0: str | None = None  # 模板编号
    field_1: str | None = None  # 模板名称
    field_2: str | None = None  # 适用场景
    field_3: str | None = None  # 预设指标
    field_4: str | None = None  # 推荐图表
    field_5: str | None = None  # 默认参数
    field_6: str | None = None  # 创建人
    field_7: str | None = None  # 模板状态

class RefreshEntry(BaseModel):
    """刷新任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 数据对象
    field_2: str | None = None  # 刷新类型
    field_3: str | None = None  # 调度表达式
    field_4: str | None = None  # 上次刷新
    field_5: str | None = None  # 下次刷新
    field_6: str | None = None  # 执行日志
    field_7: str | None = None  # 任务状态
