"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import kpi as router_kpi
from app.routers import finance as router_finance
from app.routers import sales as router_sales
from app.routers import customer as router_customer
from app.routers import supply as router_supply
from app.routers import hr as router_hr
from app.routers import forecast as router_forecast
from app.routers import alert as router_alert
from app.routers import decision as router_decision
from app.routers import drill as router_drill
from app.routers import report as router_report
from app.routers import compare as router_compare
from app.routers import datasource as router_datasource
from app.routers import cache as router_cache
from app.routers import template as router_template
from app.routers import refresh as router_refresh
from app.routers import business_detail as router_business_detail

ROUTERS = [router_kpi, router_finance, router_sales, router_customer, router_supply, router_hr, router_forecast, router_alert, router_decision, router_drill, router_report, router_compare, router_datasource, router_cache, router_template, router_refresh, router_business_detail]
