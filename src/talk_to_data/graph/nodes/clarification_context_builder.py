"""
Clarification Context Builder 节点
用于构建澄清上下文
"""

import json
from typing import Dict, Any


def create_semantic_clarification_context_builder_node():
    """创建 Semantic Clarification Context Builder 节点"""

    def builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建语义澄清上下文

        输入:
            - clarification_source: 澄清来源
            - query_state: 查询状态
            - rewritten_question: 重写后的问题

        输出:
            - clarification_context: 澄清上下文
            - clarification_context_text: 澄清上下文文本
        """
        print("\n========== SEMANTIC CLARIFICATION CONTEXT BUILDER NODE INPUT ==========")
        print(f"clarification_source: {state.get('clarification_source', {})}")
        print("======================================================================\n")

        clarification_source = state.get("clarification_source", {})
        query_state = state.get("query_state", {})
        rewritten_question = state.get("rewritten_question", "")

        # 解析澄清来源
        source = clarification_source if isinstance(clarification_source, dict) else {}

        source_type = source.get("source", "")
        clarification_type = source.get("type", "")
        reason = source.get("reason", "")
        concept = source.get("concept", "")
        candidates = source.get("candidates", [])

        clarification_context = {
            "version": 1,
            "required": True,
            "source": source_type,
            "type": clarification_type,
            "reason": reason,
            "concept": concept,
            "question": rewritten_question or "",
            "query_state": query_state,
            "candidates": candidates if isinstance(candidates, list) else []
        }

        clarification_context_text = json.dumps(clarification_context, ensure_ascii=False)

        print("\n========== SEMANTIC CLARIFICATION CONTEXT BUILDER NODE OUTPUT ==========")
        print(f"clarification_context: {clarification_context_text[:200]}...")
        print("======================================================================\n")

        return {
            "clarification_context": clarification_context,
            "clarification_context_text": clarification_context_text
        }

    return builder_node


def create_value_clarification_context_builder_node():
    """创建 Value Clarification Context Builder 节点"""

    def builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建值澄清上下文

        输入:
            - value_clarification_source: 值澄清来源
            - query_state: 查询状态

        输出:
            - value_clarification_context: 值澄清上下文
        """
        print("\n========== VALUE CLARIFICATION CONTEXT BUILDER NODE INPUT ==========")
        print(f"value_clarification_source: {state.get('value_clarification_source', {})}")
        print("====================================================================\n")

        value_clarification_source = state.get("value_clarification_source", {})
        query_state = state.get("query_state", {})

        source = value_clarification_source if isinstance(value_clarification_source, dict) else {}

        source_type = source.get("source", "")
        clarification_type = source.get("type", "")
        reason = source.get("reason", "")
        concept = source.get("concept", "")
        candidates = source.get("candidates", [])

        value_clarification_context = {
            "version": 1,
            "required": True,
            "source": source_type,
            "type": clarification_type,
            "reason": reason,
            "concept": concept,
            "query_state": query_state,
            "candidates": candidates if isinstance(candidates, list) else []
        }

        print("\n========== VALUE CLARIFICATION CONTEXT BUILDER NODE OUTPUT ==========")
        print(f"value_clarification_context: {value_clarification_context}")
        print("====================================================================\n")

        return {
            "value_clarification_context": value_clarification_context
        }

    return builder_node
