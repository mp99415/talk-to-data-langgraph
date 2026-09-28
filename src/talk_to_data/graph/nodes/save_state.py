"""
状态保存节点
"""

import json
import time
from typing import Dict, Any, List, Optional


# 模拟的会话存储（实际项目中可替换为 Redis/数据库）
_session_store: Dict[str, Any] = {}


def create_save_query_state_node():
    """
    创建保存查询状态的节点
    将 query_state 保存到会话或数据库
    """

    def save_query_state_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SAVE QUERY STATE NODE INPUT ==========")
        print(f"user_id: {state.get('user_id', '')}")
        print(f"query_state: {state.get('query_state')}")

        user_id = state.get("user_id", "")
        query_state = state.get("query_state", {})

        if not user_id:
            print("WARNING: No user_id provided, skipping save")
            return {
                "status": "SKIPPED",
                "node_timings": {"save_query_state": time.time() - start_time}
            }

        # 多轮对话支持：把执行结果中解析出的实体值（如公司名）回写到 entity.value，
        # 让下一轮 rewriter 能解析"它/那家公司/销售额是多少？"等指代和省略
        execution_result = state.get("normalized_result") or state.get("execution_result") or []
        semantic_result = state.get("semantic_result") or {}
        query_state = enrich_entity_value_from_result(query_state, execution_result, semantic_result)

        # 保存到会话存储
        session_key = f"query_state:{user_id}"
        _session_store[session_key] = {
            "query_state": query_state,
            "timestamp": time.time()
        }

        # 如果需要持久化到数据库，可以在这里添加数据库逻辑
        # save_to_database(user_id, query_state)

        elapsed = time.time() - start_time

        print(f"========== SAVE QUERY STATE NODE OUTPUT ==========")
        print(f"Saved query_state for user: {user_id}")
        print(f"[TIMER] Save Query State: {elapsed:.2f}s")
        print(f"===================================================\n")

        return {
            "status": "SUCCESS",
            "query_state": query_state,
            "node_timings": {"save_query_state": elapsed}
        }

    return save_query_state_node


def _find_entity_concept(semantic_result: Any) -> str:
    """从语义结果中查找实体概念词（公司/客户等），entity 缺失时用于补建"""
    if not isinstance(semantic_result, dict):
        return ""
    for key in ("entities", "dimensions"):
        items = semantic_result.get(key) or []
        if items and isinstance(items[0], dict):
            c = str(items[0].get("concept") or "").strip()
            if c:
                return c
    ranking = semantic_result.get("ranking")
    if isinstance(ranking, dict):
        c = str(ranking.get("concept") or "").strip()
        if c:
            return c
    extensions = semantic_result.get("extensions")
    if isinstance(extensions, dict):
        sub = extensions.get("sub_query")
        if isinstance(sub, dict):
            c = str(sub.get("entity") or "").strip()
            if c:
                return c
    return ""


def enrich_entity_value_from_result(query_state: Any, execution_result: Any, semantic_result: Any = None) -> Any:
    """
    从执行结果中提取实体值，回写到 query_state.entity.value。

    业务背景:
      问"今年销售额最高的公司是哪家？"后，SQL 结果里的公司名（如 北京云计算有限公司）
      只存在于结果行中，query_state.entity.value 仍是泛化概念词"公司"甚至 entity 为 None。
      下一轮用户问"它今年的利润是多少？/销售额是多少？"时，rewriter 无法解析指代，
      退化成查当前用户自己的数据。

    规则:
      - entity 缺失时，若语义结果解析出实体概念（公司/客户等），先补建 entity
      - value 仍是概念词（与 name 相同或为空）时才回写，不覆盖已有具体值
      - 在结果首行中按概念名/常见别名查找列（如 `公司`/`公司名`/`客户`/`name`）
      - 只接受非数字的非空字符串值（编号类值不作为实体名）
    """
    try:
        if not isinstance(query_state, dict):
            return query_state

        rows = execution_result if isinstance(execution_result, list) else []
        if not rows or not isinstance(rows[0], dict):
            return query_state
        first_row = rows[0]

        entity = query_state.get("entity")
        if isinstance(entity, dict):
            concept = str(entity.get("name") or "").strip()
        else:
            # entity 缺失（rewriter operations 不稳定导致），从语义结果补建
            concept = _find_entity_concept(semantic_result)
            if not concept or concept in ("当前用户", "我", "我的"):
                return query_state
            entity = {"name": concept, "value": ""}
            query_state["entity"] = entity

        current_value = str(entity.get("value") or "").strip()
        # value 已是具体值（非概念词本身）则不覆盖
        if current_value and current_value not in ("公司", "客户", concept):
            return query_state

        candidate_keys = {concept, "公司", "公司名", "公司名称", "客户", "客户名", "客户名称", "name"}
        for row_key, row_val in first_row.items():
            if str(row_key).strip() not in candidate_keys:
                continue
            sv = str(row_val).strip() if row_val is not None else ""
            if sv and not sv.replace(".", "").replace(",", "").isdigit():
                entity["value"] = sv
                print(f"[DEBUG][save_state] 实体值回写: entity.value = '{sv}'")
                return query_state
        return query_state
    except Exception as e:
        print(f"[DEBUG][save_state] entity 回写失败: {e}")
        return query_state


def create_clear_pending_node():
    """
    创建清除待处理状态的节点
    清除 pending_clarification 相关状态
    """

    def clear_pending_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== CLEAR PENDING NODE INPUT ==========")
        print(f"pending_clarification: {state.get('pending_clarification')}")
        print(f"pending_clarification_required: {state.get('pending_clarification_required')}")

        elapsed = time.time() - start_time

        print(f"========== CLEAR PENDING NODE OUTPUT ==========")
        print("Cleared pending clarification states")
        print(f"[TIMER] Clear Pending: {elapsed:.2f}s")
        print(f"==============================================\n")

        return {
            "pending_clarification": None,
            "pending_clarification_required": False,
            "clarification_answer": None,
            "node_timings": {"clear_pending": elapsed}
        }

    return clear_pending_node


def create_result_adapter_node():
    """
    创建结果适配器节点
    将数据库查询结果转换为标准格式
    """

    def result_adapter_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== RESULT ADAPTER NODE INPUT ==========")
        print(f"execution_result: {str(state.get('execution_result', []))[:200]}")

        execution_result = state.get("execution_result", [])

        # 适配器：将不同格式的查询结果转换为标准格式
        adapted_result = adapt_result(execution_result)

        elapsed = time.time() - start_time

        print(f"========== RESULT ADAPTER NODE OUTPUT ==========")
        print(f"Adapted result count: {len(adapted_result)}")
        print(f"[TIMER] Result Adapter: {elapsed:.2f}s")
        print(f"================================================\n")

        return {
            "execution_result": adapted_result,
            "node_timings": {"result_adapter": elapsed}
        }

    return result_adapter_node


def adapt_result(result: Any) -> Any:
    """
    适配查询结果为标准格式

    支持的输入格式:
    - List[Dict]: 直接返回
    - Dict: 包装为列表
    - str (JSON): 解析后返回
    - 其他: 转换为字符串列表
    """
    if result is None:
        return []

    # 已经是列表
    if isinstance(result, list):
        return result

    # 字典格式，检查是否包含 data/results 字段
    if isinstance(result, dict):
        # 常见的数据字段
        for key in ["data", "results", "rows", "items", "records"]:
            if key in result:
                return result[key]
        # 没有常见字段，包装为单个结果
        return [result]

    # JSON 字符串
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass

    # 其他类型，转换为字符串
    return [str(result)]


def create_result_normalizer_node():
    """
    创建结果规范化器节点
    规范化查询结果的格式和类型
    """

    def result_normalizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== RESULT NORMALIZER NODE INPUT ==========")
        print(f"execution_result: {str(state.get('execution_result', []))[:200]}")

        execution_result = state.get("execution_result", [])

        # 规范化结果
        normalized = normalize_result(execution_result)

        elapsed = time.time() - start_time

        print(f"========== RESULT NORMALIZER NODE OUTPUT ==========")
        print(f"Normalized result count: {len(normalized)}")
        print(f"[TIMER] Result Normalizer: {elapsed:.2f}s")
        print(f"==================================================\n")

        return {
            "normalized_result": normalized,
            "node_timings": {"result_normalizer": elapsed}
        }

    return result_normalizer_node


def normalize_result(result: Any) -> List[Dict]:
    """
    规范化查询结果

    处理:
    - 类型转换（日期、数字等）
    - 空值处理
    - 字段名称标准化
    """
    if not result:
        return []

    # 确保是列表
    if isinstance(result, dict):
        result = [result]
    elif not isinstance(result, list):
        result = [result]

    normalized = []

    for row in result:
        if row is None:
            continue

        normalized_row = normalize_row(row)
        normalized.append(normalized_row)

    return normalized


def normalize_row(row: Any) -> Dict:
    """
    规范化单行数据
    """
    if row is None:
        return {}

    if not isinstance(row, dict):
        return {"value": row}

    normalized = {}

    for key, value in row.items():
        # 标准化键名：转换为小写，下划线分隔
        normalized_key = key.lower().strip()

        # 处理空值
        if value is None:
            normalized[normalized_key] = None
            continue

        # 类型规范化
        normalized_value = normalize_value(value)
        normalized[normalized_key] = normalized_value

    return normalized


def normalize_value(value: Any) -> Any:
    """
    规范化单个值
    """
    # 数字类型
    if isinstance(value, (int, float)):
        # 处理 nan/inf
        if isinstance(value, float):
            import math
            if math.isnan(value) or math.isinf(value):
                return None
        return value

    # 布尔类型
    if isinstance(value, bool):
        return value

    # 字符串类型
    if isinstance(value, str):
        value = value.strip()
        # 尝试转换为数字
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        # 尝试转换为布尔
        lower = value.lower()
        if lower == "true":
            return True
        elif lower == "false":
            return False
        return value

    # 日期时间字符串
    if isinstance(value, str) and _is_datetime_string(value):
        return value

    # 其他类型直接返回
    return value


def _is_datetime_string(value: str) -> bool:
    """判断是否为日期时间字符串"""
    import re

    datetime_patterns = [
        r"^\d{4}-\d{2}-\d{2}$",  # 2024-01-01
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",  # 2024-01-01 12:00:00
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # ISO format
    ]

    for pattern in datetime_patterns:
        if re.match(pattern, value):
            return True

    return False
