"""
Graph 通用辅助函数

集中存放跨节点的复用逻辑（如 UNKNOWN_FIELD 友好提示、字段匹配等）。
"""

from typing import Dict, Any, List


def build_unknown_field_message(field: str, user_query: str, schema: dict) -> str:
    """
    构造 UNKNOWN_FIELD 类型的统一友好错误提示（简短版）。

    默认输出:
      ❌ 您查询的 字段在数据库中不存在

    Args:
        field: 用户查询中不存在的字段名（保留参数以备未来扩展）
        user_query: 用户原始问题（保留参数以备未来扩展）
        schema: 数据库 schema dict（保留参数以备未来扩展）

    Returns:
        简短的单行错误提示
    """
    return "❌ 您查询的 字段在数据库中不存在"


def infer_relevant_tables(field: str, user_query: str, tables: List[str]) -> List[str]:
    """
    根据用户问题和失败字段，推理最相关的表。

    启发式:
      1. 优先包含 user_query 中关键字的表（如"员工" → users 表）
      2. 表名前缀匹配（如 "员工" 与 "user"）
      3. 兜底返回前 3 张表

    Args:
        field: 失败的字段名
        user_query: 用户问题
        tables: 数据库所有表名

    Returns:
        排序后的相关表名列表（最多 3 张）
    """
    if not tables:
        return []
    # 中文关键词 → 表名关键词
    keyword_to_table = {
        "员工": ["users", "user"],
        "工资": ["users", "salary"],
        "客户": ["customers", "customer"],
        "订单": ["orders", "order"],
        "销售": ["orders"],
        "公司": ["customers", "companies"],
        "部门": ["departments", "department"],
    }
    user_query_lower = (user_query or "").lower()
    scored = []
    for table in tables:
        table_lower = table.lower()
        score = 0
        # 关键词匹配
        for kw, table_keywords in keyword_to_table.items():
            if kw in user_query_lower and any(tk in table_lower for tk in table_keywords):
                score += 10
        # 表名前缀匹配（如 "员工" 与 "user"）
        if "员工" in user_query_lower and "user" in table_lower:
            score += 5
        if "订单" in user_query_lower and "order" in table_lower:
            score += 5
        if "客户" in user_query_lower and "customer" in table_lower:
            score += 5
        scored.append((score, table))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:3]] if scored else tables[:3]


def infer_relevant_concepts(user_query: str) -> List[str]:
    """
    根据用户问题，推断可能相关的业务概念。
    用于在 UNKNOWN_FIELD 错误时给出"换个问法"建议。

    Args:
        user_query: 用户原始问题

    Returns:
        建议的业务概念列表
    """
    if not user_query:
        return []
    user_query_lower = user_query.lower()
    suggestions = []
    if "员工" in user_query_lower or "工资" in user_query_lower:
        suggestions.extend(["员工人数", "员工部门分布", "员工地区分布"])
    if "客户" in user_query_lower:
        suggestions.extend(["客户数量", "客户地区分布", "客户订单量"])
    if "订单" in user_query_lower:
        suggestions.extend(["订单数量", "订单金额", "订单地区分布"])
    if "销售" in user_query_lower:
        suggestions.extend(["销售额", "销售员业绩排名", "销售区域排名"])
    if not suggestions:
        suggestions = ["相关数据统计", "数据趋势分析", "数据对比"]
    return suggestions[:5]