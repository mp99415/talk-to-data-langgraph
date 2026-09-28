"""
Schema Test Override 节点
用于测试时覆盖 schema
"""

import json
from typing import Dict, Any


def create_schema_test_override_node():
    """创建 Schema Test Override 节点"""

    def schema_test_override_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Schema 测试覆盖

        输入:
            - schema_context: Schema 上下文

        输出:
            - schema_context: 处理后的 schema
        """
        print("\n========== SCHEMA TEST OVERRIDE NODE INPUT ==========")
        print(f"schema_context: {str(state.get('schema_context', {}))[:200]}...")
        print("=======================================================\n")

        schema_context = state.get("schema_context", {})

        # 解析 schema_context
        if isinstance(schema_context, str):
            try:
                schema_context = json.loads(schema_context)
            except:
                schema_context = {}

        # 简化版：直接返回原始 schema
        # 完整实现可以根据测试需求覆盖某些字段

        print("\n========== SCHEMA TEST OVERRIDE NODE OUTPUT ==========")
        print(f"schema_context: {str(schema_context)[:200]}...")
        print("=======================================================\n")

        return {"schema_context": schema_context}

    return schema_test_override_node
