"""
Value Lookup Prep 节点
用于准备值语义查找
"""

from typing import Dict, Any, List


def create_value_lookup_prep_node():
    """创建 Value Lookup Prep 节点"""

    def value_lookup_prep_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备值语义查找

        输入:
            - semantic_result: 语义解析结果
            - query_state: 查询状态

        输出:
            - lookup_items: 需要查找的项列表
            - lookup_required: 是否需要查找
        """
        print("\n========== VALUE LOOKUP PREP NODE INPUT ==========")
        print(f"semantic_result: {state.get('semantic_result', {})}")
        print("================================================\n")

        semantic_result = state.get("semantic_result", {})
        query_state = state.get("query_state", {})

        lookup_items = []
        lookup_required = False

        # 从语义结果中提取需要值查找的项
        filters = semantic_result.get("filters", [])
        for f in filters:
            # 检查是否有需要查找的值
            if "value" in f and f.get("match_type") == "VALUE_MATCH":
                # 值匹配，需要查找
                lookup_items.append({
                    "type": "filter_value",
                    "field": f.get("field", ""),
                    "value": f.get("value", ""),
                    "business_value": f.get("business_value", "")
                })
                lookup_required = True

        # 检查 entity
        entity = query_state.get("entity")
        if entity and entity.get("value") is None:
            # entity 没有值，需要查找
            lookup_items.append({
                "type": "entity",
                "concept": entity.get("name", ""),
                "value": entity.get("value")
            })
            lookup_required = True

        print("\n========== VALUE LOOKUP PREP NODE OUTPUT ==========")
        print(f"lookup_items: {lookup_items}")
        print(f"lookup_required: {lookup_required}")
        print("================================================\n")

        return {
            "lookup_items": lookup_items,
            "lookup_required": lookup_required
        }

    return value_lookup_prep_node
