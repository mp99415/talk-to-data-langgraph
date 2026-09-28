"""
Answer Validator 节点
用于验证澄清问题的答案
"""

from typing import Dict, Any


def create_answer_validator_node():
    """创建 Answer Validator 节点"""

    def answer_validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证澄清答案的有效性

        输入:
            - clarification_answer: 用户的澄清答案
            - pending_clarification: 待处理的澄清

        输出:
            - is_valid: 答案是否有效
            - validated_answer: 验证后的答案
        """
        print("\n========== ANSWER VALIDATOR NODE INPUT ==========")
        print(f"clarification_answer: {state.get('clarification_answer', {})}")
        print(f"pending_clarification: {state.get('pending_clarification', {})}")
        print("================================================\n")

        clarification_answer = state.get("clarification_answer", {})
        pending_clarification = state.get("pending_clarification", {})

        is_valid = True
        error_message = ""

        # 检查答案是否为空
        if not clarification_answer:
            is_valid = False
            error_message = "答案不能为空"
        elif not isinstance(clarification_answer, dict):
            is_valid = False
            error_message = "答案格式错误"
        else:
            # 检查答案是否包含必要的字段
            # 根据澄清类型验证
            clarification_type = pending_clarification.get("type", "")

            if clarification_type == "FIELD":
                # 字段澄清，需要验证字段选择
                if "selected_field" not in clarification_answer:
                    is_valid = False
                    error_message = "请选择字段"
            elif clarification_type == "VALUE":
                # 值澄清，需要验证值
                if "selected_value" not in clarification_answer:
                    is_valid = False
                    error_message = "请选择值"

        print("\n========== ANSWER VALIDATOR NODE OUTPUT ==========")
        print(f"is_valid: {is_valid}")
        print(f"error_message: {error_message}")
        print("================================================\n")

        return {
            "answer_validator_result": {
                "is_valid": is_valid,
                "error_message": error_message
            },
            "validated_answer": clarification_answer if is_valid else {}
        }

    return answer_validator_node
