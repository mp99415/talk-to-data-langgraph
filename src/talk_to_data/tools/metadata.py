"""
元数据工具
"""

import json
from typing import Dict, Any, List
from langchain_core.tools import tool


@tool("get_business_metadata")
def get_business_metadata_tool() -> str:
    """
    获取业务元数据
    
    返回业务表、字段、业务含义等元信息
    """
    metadata = {
        "tables": [
            {
                "table_name": "customers",
                "business_name": "客户",
                "columns": [
                    {"field": "customer_id", "business_name": "客户ID", "type": "varchar"},
                    {"field": "customer_name", "business_name": "客户名称", "type": "varchar"},
                    {"field": "region", "business_name": "地区", "type": "varchar"},
                    {"field": "industry", "business_name": "行业", "type": "varchar"},
                ]
            },
            {
                "table_name": "orders",
                "business_name": "订单",
                "columns": [
                    {"field": "order_id", "business_name": "订单ID", "type": "varchar"},
                    {"field": "customer_id", "business_name": "客户ID", "type": "varchar"},
                    {"field": "order_date", "business_name": "订单日期", "type": "date"},
                    {"field": "amount", "business_name": "金额", "type": "decimal"},
                    {"field": "region", "business_name": "销售区域", "type": "varchar"},
                ]
            },
            {
                "table_name": "products",
                "business_name": "产品",
                "columns": [
                    {"field": "product_id", "business_name": "产品ID", "type": "varchar"},
                    {"field": "product_name", "business_name": "产品名称", "type": "varchar"},
                    {"field": "category", "business_name": "类别", "type": "varchar"},
                    {"field": "price", "business_name": "价格", "type": "decimal"},
                ]
            }
        ]
    }
    
    return json.dumps(metadata, ensure_ascii=False)


# 导出底层函数供直接调用
def get_business_metadata_func() -> str:
    """获取业务元数据（底层函数）"""
    return get_business_metadata_tool()
