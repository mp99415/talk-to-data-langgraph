"""
路由逻辑
"""

from typing import Dict, Any


def intent_router(state: Dict[str, Any]) -> str:
    """意图路由"""
    intent = state.get("intent", "DATA_QUERY")
    
    if intent == "DATA_QUERY":
        return "query"
    elif intent == "UNSAFE":
        return "unsafe"
    else:
        return "general"


def query_state_router(state: Dict[str, Any]) -> str:
    """Query State 路由"""
    status = state.get("query_state_status", "")
    errors = state.get("validation_errors", [])
    
    if errors:
        return "error"
    elif status == "AMBIGUOUS":
        return "ambiguous"
    else:
        return "continue"


def sql_validator_router(state: Dict[str, Any]) -> str:
    """SQL 验证路由

    决策:
      1. valid=True + 无 UNKNOWN_FIELD warnings → valid（继续到 permission_engine）
      2. valid=True + 有 UNKNOWN_FIELD warnings → invalid（跳到 summarizer，友好提示）
      3. valid=False → invalid（危险关键字等）
    """
    result = state.get("validation_result", {})

    if not result.get("valid", False):
        return "invalid"
    # valid=True 但有 UNKNOWN_FIELD 警告 → 视为 invalid，避免 DB 报错
    warnings = result.get("warnings", []) or []
    has_unknown_field = any(w.get("type") == "UNKNOWN_FIELD" for w in warnings)
    if has_unknown_field:
        return "invalid"
    return "valid"


def security_router(state: Dict[str, Any]) -> str:
    """安全验证路由"""
    result = state.get("security_result", {})
    
    if result.get("allowed", False):
        return "allowed"
    return "forbidden"


def result_validator_router(state: Dict[str, Any]) -> str:
    """结果验证路由"""
    if state.get("validation_passed", False):
        return "valid"
    return "invalid"


def semantic_resolution_router(state: Dict[str, Any]) -> str:
    """语义解析路由"""
    if state.get("semantic_resolution_required", False):
        return "clarification"
    return "continue"


def value_semantic_router(state: Dict[str, Any]) -> str:
    """值语义路由"""
    result = state.get("value_semantic_result", {})
    
    if result.get("resolved", False):
        return "resolved"
    return "needs_clarification"


def clarification_router(state: Dict[str, Any]) -> str:
    """澄清路由"""
    answer = state.get("clarification_answer", {})
    status = answer.get("status", "")
    
    if status == "ANSWERED":
        return "answered"
    return "pending"
