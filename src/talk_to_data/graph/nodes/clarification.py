"""
澄清流程节点
"""

import json
from typing import Dict, Any
from ...llm.client import get_llm


def create_clarification_generator_node():
    """创建 CLARIFICATION GENERATOR 节点"""

    def generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== CLARIFICATION GENERATOR NODE INPUT ==========")
        print(f"user_query: {state.get('user_query', '')}")
        print(f"query_state: {state.get('query_state', {})}")
        print(f"semantic_result: {state.get('semantic_result', {})}")
        print(f"=========================================================\n")

        user_query = state.get("user_query", "")
        query_state = state.get("query_state", {})

        clarification = {
            "type": "FIELD",
            "target": {"concept": "地区"},
            "question": "你指的是客户所在地区，还是销售区域？",
            "candidates": [
                {"id": "customers.region", "label": "客户所在地区"},
                {"id": "orders.region", "label": "销售区域"}
            ],
            "status": "PENDING"
        }

        print(f"\n========== CLARIFICATION GENERATOR NODE OUTPUT ==========")
        print(f"clarification: {clarification}")
        print(f"=========================================================\n")

        return {"clarification": clarification}

    return generator_node


def create_clarification_state_builder_node():
    """创建 CLARIFICATION STATE BUILDER 节点"""

    def builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== CLARIFICATION STATE BUILDER NODE INPUT ==========")
        print(f"clarification_answer: {state.get('clarification_answer', {})}")
        print(f"=============================================================\n")

        clarification_answer = state.get("clarification_answer", {})

        if not clarification_answer:
            print(f"\n========== CLARIFICATION STATE BUILDER NODE OUTPUT ==========")
            print(f"operations: []")
            print(f"=============================================================\n")
            return {"operations": []}

        operation = {
            "operation": "REPLACE",
            "target": "FILTER",
            "value": {}
        }

        print(f"\n========== CLARIFICATION STATE BUILDER NODE OUTPUT ==========")
        print(f"operations: {[operation]}")
        print(f"=============================================================\n")

        return {"operations": [operation]}

    return builder_node
