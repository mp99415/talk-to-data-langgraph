"""
Semantic Resolution Router 节点
用于路由语义解析结果
"""

from typing import Dict, Any


def create_semantic_resolution_router_node():
    """创建 Semantic Resolution Router 节点"""

    def router_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        路由语义解析结果

        输入:
            - semantic_result: 语义解析结果

        输出:
            - route: 路由目标 (continue / clarification / error)
        """
        print("\n========== SEMANTIC RESOLUTION ROUTER NODE INPUT ==========")
        print(f"semantic_result: {state.get('semantic_result', {})}")
        print("============================================================\n")

        semantic_result = state.get("semantic_result", {})

        # 检查状态
        status = semantic_result.get("status", "")
        clarification = semantic_result.get("clarification", {})
        clarification_required = clarification.get("required", False)

        if status == "RESOLVED":
            # 解析成功
            route = "continue"
        elif status == "NEED_CLARIFICATION" or clarification_required:
            # 需要澄清（支持多种状态格式）
            route = "clarification"
        else:
            # 解析失败
            route = "error"

        print("\n========== SEMANTIC RESOLUTION ROUTER NODE OUTPUT ==========")
        print(f"route: {route}")
        print("============================================================\n")

        # 保留 semantic_result 到输出
        return {
            "semantic_resolution_route": route,
            "route": route,
            "semantic_result": semantic_result
        }

    return router_node
