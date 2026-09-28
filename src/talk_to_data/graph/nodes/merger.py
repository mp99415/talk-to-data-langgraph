"""
QUERY STATE MERGER 节点
"""

import json
import copy
import time
from typing import Dict, Any


def create_merger_node():
    """创建 QUERY STATE MERGER 节点"""

    def merger_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== MERGER NODE INPUT ==========")
        print(f"previous_query_state: {state.get('previous_query_state')}")
        print(f"operations: {state.get('operations')}")
        print(f"relation: {state.get('relation')}")

        from ..state import create_empty_query_state

        previous_state = state.get("previous_query_state") or {}
        operations = state.get("operations", [])
        relation = state.get("relation", "")

        if not previous_state:
            current_state = create_empty_query_state()
        else:
            current_state = copy.deepcopy(previous_state)

        if relation == "NEW_TOPIC":
            current_state = create_empty_query_state()

        normalized_ops = normalize_operations(operations)

        for op in normalized_ops:
            apply_operation(current_state, op)

        try:
            query_state_text = json.dumps(current_state, ensure_ascii=False)
        except:
            query_state_text = "{}"

        elapsed = time.time() - start_time

        print(f"========== MERGER NODE OUTPUT ==========")
        print(f"query_state: {current_state}")
        print(f"[TIMER] Merger: {elapsed:.2f}s")
        print(f"==========================================\n")

        return {
            "query_state": current_state,
            "query_state_text": query_state_text,
            "status": "SUCCESS",
            "node_timings": {"merger": elapsed}
        }

    return merger_node


def normalize_operations(operations):
    """标准化操作列表"""
    if operations is None:
        return []
    
    if isinstance(operations, str):
        try:
            parsed = json.loads(operations)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except:
            return []
    
    if isinstance(operations, dict):
        return [operations]
    
    if isinstance(operations, list):
        return operations
    
    return []


def apply_operation(state: Dict[str, Any], operation: Dict[str, Any]):
    """应用单个操作"""
    op = operation.get("operation", "ADD")
    if isinstance(op, str):
        op = op.upper()
    else:
        op = "ADD"

    # 处理 target 可能是 dict 或 string
    target = operation.get("target", "")
    if isinstance(target, dict):
        target = target.get("type", "")
    if isinstance(target, str):
        target = target.upper()
    else:
        target = ""

    value = operation.get("value")
    
    if op == "ADD":
        apply_add(state, target, value)
    elif op == "REMOVE":
        apply_remove(state, target, value)
    elif op == "REPLACE":
        apply_replace(state, target, value)


def apply_add(state: Dict[str, Any], target: str, value: Any):
    """应用 ADD 操作"""
    if target == "ENTITY":
        state["entity"] = copy.deepcopy(value)
    elif target == "METRIC":
        if not isinstance(state.get("metrics"), list):
            state["metrics"] = []
        state["metrics"].append(copy.deepcopy(value))
    elif target == "DIMENSION":
        if not isinstance(state.get("dimensions"), list):
            state["dimensions"] = []
        state["dimensions"].append(copy.deepcopy(value))
    elif target == "FILTER":
        if not isinstance(state.get("filters"), list):
            state["filters"] = []
        state["filters"].append(copy.deepcopy(value))
    elif target == "TIME":
        state["time"] = copy.deepcopy(value)
    elif target == "RANKING":
        state["ranking"] = copy.deepcopy(value)
    elif target == "COMPARISON":
        state["comparison"] = copy.deepcopy(value)


def apply_remove(state: Dict[str, Any], target: str, value: Any):
    """应用 REMOVE 操作"""
    if target == "ENTITY":
        state["entity"] = None
    elif target == "METRIC":
        state["metrics"] = []
    elif target == "DIMENSION":
        state["dimensions"] = []
    elif target == "FILTER":
        if value is None:
            state["filters"] = []
        else:
            state["filters"] = [f for f in state.get("filters", []) if f != value]
    elif target == "TIME":
        state["time"] = None
    elif target == "RANKING":
        state["ranking"] = None
    elif target == "COMPARISON":
        state["comparison"] = None


def apply_replace(state: Dict[str, Any], target: str, value: Any):
    """应用 REPLACE 操作"""
    apply_remove(state, target, None)
    apply_add(state, target, value)
