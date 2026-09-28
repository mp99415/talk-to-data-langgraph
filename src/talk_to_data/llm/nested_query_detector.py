"""
嵌套查询检测模块

提供嵌套查询的正则兜底检测和子查询指标的物理字段解析。
主检测路径由语义解析 LLM 完成（业务规则第八章），本模块仅作兜底。
"""

from typing import Dict, Any, Optional
import json
import re

from .client import get_llm


def quick_detect_nested_query(question: str) -> Optional[Dict[str, Any]]:
    """
    快速检测嵌套查询（不调用 LLM，使用正则）

    作为语义解析 LLM 漏检时的确定性兜底
    """
    import re

    # 定义嵌套查询模式
    # 注意：支持口语化表达，如 "公司成本" 代替 "公司的成本"
    patterns = [
        # 标准写法：X最高的公司的Y
        (r'(.+)最高的公司的(.+)是多少', '最高', '公司', 2),
        # 口语写法：X最高的公司的Y → X最高的公司Y（省略"的"）
        # 公司 + 指标
        (r'(.+)最高的公司(成本|利润|销售额|订单量|订单数)是多少', '最高', '公司', 2),
        # 客户 + 指标
        (r'(.+)最高的客户(成本|利润|销售额|订单量|订单数)是多少', '最高', '客户', 2),
        # X最低的公司的Y
        (r'(.+)最低的公司的(.+)是多少', '最低', '公司', 2),
        (r'(.+)最低的公司(成本|利润|销售额|订单量|订单数)是多少', '最低', '公司', 2),
        # X最多的客户的Y
        (r'(.+)最多的客户(.+)是多少', '最多', '客户', 2),
        (r'(.+)最多的客户(成本|利润|销售额|订单量|订单数)是多少', '最多', '客户', 2),
        # X最多的公司的Y
        (r'(.+)最多的公司(.+)是多少', '最多', '公司', 2),
        (r'(.+)最多的公司(成本|利润|销售额|订单量|订单数)是多少', '最多', '公司', 2),
        # X前N的公司的Y
        (r'(.+)前(\d+)的公司的(.+)是多少', '排名', '公司', 3),
        # 口语写法：X前N的公司Y（省略"的"）
        (r'(.+)前(\d+)的公司(成本|利润|销售额|订单量|订单数)是多少', '排名', '公司', 3),
        # X前N的客户的Y
        (r'(.+)前(\d+)的客户(.+)是多少', '排名', '客户', 3),
        # X最多的供应商的Y
        (r'(.+)最多的供应商(.+)是多少', '最多', '供应商', 2),
        # X最多的经销商的Y
        (r'(.+)最多的经销商(.+)是多少', '最多', '经销商', 2),
    ]

    for pattern, ranking, entity, metric_group_idx in patterns:
        match = re.search(pattern, question)
        if match:
            # 提取子查询指标（去掉时间前缀）
            raw_metric = match.group(1).strip()
            sub_metric = re.sub(r'^(今年|去年|前年|上个月|上个季度|最近)\s*', '', raw_metric)

            # 提取当前指标（使用 pattern 中指定的组索引）
            if ranking == '排名':
                current_metric = match.group(3).strip()
                limit = int(match.group(2))
            else:
                current_metric = match.group(metric_group_idx).strip()
                limit = 1

            # 确定排序方向
            ranking_value = "DESC" if ranking in ['最高', '最多'] else "ASC"

            # 排除简单查询（子指标和当前指标相同）
            if sub_metric != current_metric:
                result = {
                    "is_nested": True,
                    "sub_query": {
                        "metric": sub_metric,
                        "entity": entity,
                        "ranking": ranking_value,
                        "limit": limit
                    }
                }
                print(f"[DEBUG] 快速检测到嵌套查询: {result}")
                return result

    return {"is_nested": False, "sub_query": None}


def resolve_metric_field(metric_name: str, schema_context: str, llm_client=None) -> Optional[Dict[str, Any]]:
    """
    根据数据库表结构，解析业务指标对应的物理字段

    用于嵌套查询场景：semantic_result.metrics 只包含当前查询指标，
    子查询指标（如"销售额最高的公司利润"中的"销售额"）需要单独解析。

    Args:
        metric_name: 业务指标名（如"销售额"）
        schema_context: 数据库表结构文本
        llm_client: LLM 客户端

    Returns:
        {"table": "orders", "field": "amount", "aggregation": "SUM"} 或 None
    """
    if not metric_name:
        return None

    if llm_client is None:
        llm_client = get_llm()

    prompt = f"""根据数据库表结构，找出业务指标"{metric_name}"对应的物理字段。

{schema_context}

要求：
1. field 必须是 Schema 中真实存在的物理字段名
2. aggregation 只能是 SUM、COUNT、COUNT_DISTINCT、AVG、MAX、MIN 之一

只输出JSON（不要其他内容）：
{{"table": "表名", "field": "字段名", "aggregation": "SUM"}}"""

    try:
        response = llm_client.invoke(prompt)
        content = response.content.strip()

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            if result.get("table") and result.get("field"):
                print(f"[DEBUG] 子查询指标字段解析: {metric_name} -> {result}")
                return result
    except Exception as e:
        print(f"[DEBUG] 子查询指标字段解析失败: {e}")

    return None
