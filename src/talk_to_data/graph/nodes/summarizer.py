"""
结果总结节点
"""
import json
import re
import time
from typing import Dict, Any
from ...llm.client import get_llm
from ...llm.prompts import RESULT_SUMMARIZER_PROMPT, GENERAL_ANSWER_PROMPT


def _is_user_in_scope(user_id: str, user_scope: dict, current_user_id: str) -> bool:
    """
    判断 user_id 是否在 user_scope 允许范围内。
    用于 summarizer 检查 SQL 中的 owner 字段过滤值是否合法（兜底）。

    返回 True 表示允许，False 表示不允许。

    注意：user_scope=None 表示未配置（DB 不可达），应宽松处理（不强制限制）。
    """
    if not user_scope:
        # DB 不可达时降级：宽松处理（不强制限制）
        return True
    scope_type = user_scope.get("scope_type", "self")
    if scope_type == "all":
        return True
    if scope_type == "self":
        return str(user_id) == str(current_user_id)
    allowed = user_scope.get("allowed_user_ids") or []
    return str(user_id) in {str(x) for x in allowed}


def _extract_db_error(execution_result) -> str:
    """从 execution_result 提取 DB 错误信息（如果有）"""
    if not isinstance(execution_result, list) or not execution_result:
        return ""
    first = execution_result[0]
    if not isinstance(first, dict):
        return ""
    err = first.get("error", "")
    return str(err) if err else ""


def _classify_db_error(error_msg: str):
    """
    分类 DB 错误，识别字段不存在等常见错误。

    返回:
      error_type: "UNKNOWN_FIELD" | "UNKNOWN_TABLE" | "SYNTAX_ERROR" |
                  "CONNECTION_ERROR" | "PERMISSION_DENIED" | "OTHER"
      field_hint: 错误中提到的字段名（如果是字段错误）
    """
    if not error_msg:
        return "OTHER", ""
    err_lower = error_msg.lower()
    field_match = re.search(
        r"['`]?([A-Za-z_][A-Za-z0-9_]*)['`]?\s*(?:in\s*['`]?field\s*list['`]?|doesn't\s*exist)",
        error_msg,
        re.IGNORECASE,
    )
    field_hint = field_match.group(1) if field_match else ""
    if "unknown column" in err_lower or "field list" in err_lower:
        return "UNKNOWN_FIELD", field_hint
    if "doesn't exist" in err_lower and field_hint:
        # 可能是字段或表
        if field_hint.lower() in ("id", "name", "type", "status", "field"):
            return "UNKNOWN_FIELD", field_hint
        return "UNKNOWN_TABLE", field_hint
    if "table" in err_lower and "doesn't exist" in err_lower:
        return "UNKNOWN_TABLE", field_hint
    if "syntax error" in err_lower or "your sql syntax" in err_lower:
        return "SYNTAX_ERROR", field_hint
    if "access denied" in err_lower or "permission" in err_lower:
        return "PERMISSION_DENIED", field_hint
    if "connect" in err_lower or "connection" in err_lower or "timed out" in err_lower:
        return "CONNECTION_ERROR", field_hint
    return "OTHER", field_hint


def _build_friendly_error_message(
    error_type: str,
    field_hint: str,
    user_query: str,
    sql: str,
) -> str:
    """
    根据错误分类生成友好的用户提示。

    友好提示包括:
    - 错误原因说明
    - 建议下一步操作（如改问法、查别的字段）
    - 数据库实际有的相关字段（如果可获得）
    """
    base_msg = ""
    suggestions = []

    if error_type == "UNKNOWN_FIELD":
        base_msg = f"您查询的 `{field_hint}` 字段在数据库中不存在。"
        suggestions = [
            "查询其他可能相关的字段",
            "换个问法（如'员工收入'、'员工薪资构成'）",
            f"如确认需要 `{field_hint}` 字段，请联系管理员建表或字段",
        ]
    elif error_type == "UNKNOWN_TABLE":
        base_msg = f"查询涉及的表 `{field_hint}` 在数据库中不存在。"
        suggestions = [
            "换个相关的业务概念提问",
            "确认是否需要其他表的数据",
        ]
    elif error_type == "SYNTAX_ERROR":
        base_msg = "查询生成的 SQL 存在语法错误，无法执行。"
        suggestions = [
            "换个说法重新提问",
            "如反复出现此问题，请联系系统管理员",
        ]
    elif error_type == "CONNECTION_ERROR":
        base_msg = "数据库连接异常，无法执行查询。"
        suggestions = [
            "稍后重试",
            "如持续异常，请联系系统管理员",
        ]
    elif error_type == "PERMISSION_DENIED":
        base_msg = "您没有权限访问相关数据。"
        suggestions = [
            "联系管理员申请相应权限",
        ]
    else:
        base_msg = "查询执行遇到错误。"
        suggestions = [
            "换个问法重新提问",
            "如反复出现，请联系系统管理员",
        ]

    # 尝试从 schema 中推荐相似字段
    similar_fields_hint = ""

    full_msg = base_msg
    if suggestions:
        full_msg += "\n建议：\n" + "\n".join(f"- {s}" for s in suggestions)
    return full_msg


def _extract_owner_filter_values_from_sql(sql: str) -> list:
    """
    从 SQL WHERE 子句中提取 owner 字段（sales_id）的字面量值。
    返回 ["1002", "1003", ...] 列表。
    """
    if not sql:
        return []
    try:
        # 找 WHERE 子句
        upper = sql.upper()
        where_idx = upper.rfind(" WHERE ")
        if where_idx < 0:
            return []
        where_part = sql[where_idx + 7:]
        # 截断到 GROUP BY / HAVING / ORDER BY / LIMIT
        for kw in (" GROUP BY ", " HAVING ", " ORDER BY ", " LIMIT "):
            idx = where_part.upper().find(kw)
            if idx >= 0:
                where_part = where_part[:idx]

        values = []
        owner_field_pattern = r"`?(?:\w+\.)?`?(sales_id|owner_id|creator_id|assignee_id|approver_id|agent_id|created_by|manager_id|created_by_id|updated_by_id|user_id|operator_id)`?"

        # 模式 1: field = 'value' / field = '1001'
        p_single = re.compile(
            rf"{owner_field_pattern}\s*(=|==)\s*(?P<val>'[^']*'|\d+)",
            re.IGNORECASE,
        )
        for m in p_single.finditer(where_part):
            v = m.group("val").strip("'\"")
            if v:
                values.append(v)

        # 模式 2: field IN ('v1', 'v2', ...)
        p_in = re.compile(
            rf"{owner_field_pattern}\s+IN\s*\((?P<list>[^)]+)\)",
            re.IGNORECASE,
        )
        for m in p_in.finditer(where_part):
            inner = m.group("list")
            for v in re.findall(r"'([^']*)'|\"([^\"]*)\"|(\d+)", inner):
                val = next((x for x in v if x), "")
                if val:
                    values.append(val)

        return list(dict.fromkeys(values))
    except Exception:
        return []


def create_result_summarizer_node():
    """创建 RESULT SUMMARIZER 节点"""

    def summarizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SUMMARIZER NODE INPUT ==========")
        print(f"execution_result: {str(state.get('execution_result', []))[:300]}")
        print(f"sql: {state.get('sql', '')}")
        print(f"user_query: {state.get('user_query', '')}")

        # 权限拦截短路：不再调 LLM，直接返回明确错误信息
        if state.get("sql_execution_blocked"):
            block_msg = state.get("permission_block_message") or "权限不足，无法执行该查询"
            print(f"[FORBIDDEN] {block_msg}")
            return {
                "summarized_result": block_msg,
                "final_answer": block_msg,
                "node_timings": {"summarizer": time.time() - start_time},
            }

        # 兜底拦截：summarizer 在生成答案前再次确认 owner 字段过滤值在 user_scope 内。
        # 正常情况下 permission_engine 已经拦截过，这里只是双保险。
        # 如果 SQL 已经执行（execution_result 非空）但 owner 字段过滤值不在 scope 内，
        # 说明 permission_engine 漏判，summarizer 必须兜底拒绝。
        user_info_list_for_check = state.get("user_info", []) or []
        if isinstance(user_info_list_for_check, list) and user_info_list_for_check:
            current_user_id_check = str(user_info_list_for_check[0].get("user_id") or "")
            user_scope_check = state.get("user_scope") or None
            sql_check = state.get("sql", "")
            owner_values = _extract_owner_filter_values_from_sql(sql_check)
            if current_user_id_check and owner_values and user_scope_check is not None:
                out_of_scope = [
                    v for v in owner_values
                    if not _is_user_in_scope(v, user_scope_check, current_user_id_check)
                ]
                if out_of_scope:
                    scope_msg = (
                        f"权限不足：您查询的 owner 字段值 {out_of_scope} 不在您的可查询范围内。"
                        "如需查询他人的数据，请联系管理员申请相应权限。"
                    )
                    print(f"[INFO] summarizer 兜底拦截 owner 失败: {out_of_scope}")
                    return {
                        "summarized_result": scope_msg,
                        "final_answer": scope_msg,
                        "node_timings": {"summarizer": time.time() - start_time},
                    }

        # 方案 B：行级策略收窄了 SQL（应用了用户/region 过滤）但 LLM 把结果当成"全部数据"回答
        # 检测模式：
        #   1. 用户问题涉及"他人/其他人/全部/所有"等查询
        #   2. row_policy_applied=True 说明真的是被行级策略收窄（permission_engine 已记录）
        #   3. 当前 SQL 含 owner 字段（sales_id 等）=当前用户 的过滤条件（row policy 收窄结果）
        #   4. 或者 LLM 答案里提到 owner 关键词（张三/李四/全部），但实际只返回 1-2 行数据（极可能 LLM 编造了数据）
        # 直接覆盖 LLM 答案，避免误导
        #
        # 注意：permission_engine 已经基于 user_scope 授权了 owner 字段过滤。
        # 如果 SQL 通过了 permission_engine，说明 owner 字段过滤值在用户可查询范围内。
        # 这里只拦截"被行级策略自动收窄 + LLM 误以为返回的就是全部"的情况，
        # 不应重复拦截"用户主动查询他人"（permission_engine 已经判断权限）。
        execution_result = state.get("execution_result", [])
        sql = state.get("sql", "")
        q = state.get("rewritten_question") or state.get("user_query") or ""
        # 扩大关键词检测
        other_query_words = [
            "其他销售", "其他人", "其他", "全部", "所有人", "所有",
            "都不是我", "整个公司", "全公司", "每人",
        ]
        asks_for_others = any(w in q for w in other_query_words)
        if asks_for_others and execution_result:
            # 检测 SQL 中是否被强制追加了 owner 字段过滤（即含 sales_id=当前用户）
            user_info_list = state.get("user_info", []) or []
            current_user_id = None
            current_region = None
            current_username = ""
            current_name = ""
            if isinstance(user_info_list, list) and user_info_list:
                u = user_info_list[0]
                if isinstance(u, dict):
                    current_user_id = str(u.get("user_id") or "")
                    current_region = str(u.get("region") or "")
                    current_username = str(u.get("username") or "")
                    current_name = str(u.get("name") or "")
            narrow_owner = False
            narrow_region = False
            if current_user_id and re.search(rf"`?sales_id`?\s*=\s*'{re.escape(current_user_id)}'", sql, re.IGNORECASE):
                narrow_owner = True
            if current_region and re.search(rf"`?region`?\s*=\s*'{re.escape(current_region)}'", sql, re.IGNORECASE):
                narrow_region = True
            # 关键修复：row_policy_applied=True 才说明是真的"被策略收窄"，
            # 否则 SQL 里的 sales_id=current_user_id 是用户自己要求的（"我的"/"我名下的"），
            # 此时不应拦截。王总（role=4 无 row_policy）查"所有销售人员的销售额" SQL 不会含 sales_id=1004，
            # 所以也不会误拦截。
            row_policy_applied = bool(state.get("row_policy_applied"))
            # 用户显式查询他人名字（如"查询李四的销售额"）的拦截判断：
            # 由 permission_engine 已基于 user_scope 判断过权限，summarizer 不应重复拦截。
            # 只有 permission_engine 没拦截（即授权成功），summarizer 才不会拦截。
            # 因此：只有当 SQL 已被 permission_engine 拦截（sql_execution_blocked=True）但我们到这里
            # 说明 sql 是执行了的（execution_result 非空），这种情况不应该走到这里。
            # 旧的"target_others 拦截"已经被 permission_engine 替代，summarizer 不再做硬编码人名拦截。
            # 只有 row_policy_applied 才说明真的被策略收窄了 → 拦截
            # 否则 SQL 里的 owner 过滤是用户自己要求的（如"我的销售额"/"我的订单"），不拦截
            if (narrow_owner or narrow_region) and row_policy_applied:
                scope_msg = (
                    "您当前的查询被行级权限收窄，只能查看您个人负责的数据，"
                    "无法查看其他销售人员/区域的相关数据。"
                    "如需查询他人的数据，请联系管理员申请相应权限。"
                )
                print(f"[INFO] row_policy_narrow with other-query: {scope_msg}")
                return {
                    "summarized_result": scope_msg,
                    "final_answer": scope_msg,
                    "node_timings": {"summarizer": time.time() - start_time},
                }

        # summarizer 需要一定的创造性来生成自然语言回答
        llm = get_llm(temperature=0.7)

        execution_result = state.get("execution_result", [])
        sql = state.get("sql", "")
        user_query = state.get("user_query", "")
        rewritten_question = state.get("rewritten_question", user_query)
        query_state = state.get("query_state_text", "{}")

        # ========== SQL 执行错误友好处理 ==========
        # 如果 execution_result 含 error 字段（DB 执行失败），直接给出友好错误，
        # 避免 LLM 把 DB 错误机械地翻译成"建议检查表结构"
        db_error_msg = _extract_db_error(execution_result)
        if db_error_msg:
            # 解析错误类型 + 给出建议
            error_type, field_hint = _classify_db_error(db_error_msg)
            if error_type == "UNKNOWN_FIELD":
                # UNKNOWN_FIELD 走统一的友好模板（与 error_answer 节点保持一致）
                from ..graph_helpers import build_unknown_field_message
                validation_result = build_unknown_field_message(
                    field=field_hint,
                    user_query=user_query or rewritten_question,
                    schema=state.get("schema", {}),
                )
            else:
                validation_result = _build_friendly_error_message(
                    error_type=error_type,
                    field_hint=field_hint,
                    user_query=user_query or rewritten_question,
                    sql=sql,
                )
            print(f"[INFO] SQL 执行错误（友好提示）: {validation_result[:200]}")
            return {
                "summarized_result": validation_result,
                "final_answer": validation_result,
                "node_timings": {"summarizer": time.time() - start_time},
            }

        try:
            result_str = json.dumps(execution_result, ensure_ascii=False, default=str)
        except:
            result_str = str(execution_result)

        # 根据结果是否为空设置 validation_result
        if not execution_result or len(execution_result) == 0:
            validation_result = "EMPTY"
        else:
            validation_result = "VALID"

        # 简化的 prompt（使用已有的变量）
        prompt = RESULT_SUMMARIZER_PROMPT.format(
            user_question=rewritten_question,
            query_plan=query_state,
            result=result_str,
            validation_result=validation_result
        )

        response = llm.invoke(prompt)

        elapsed = time.time() - start_time

        print(f"========== SUMMARIZER NODE OUTPUT ==========")
        print(f"final_answer: {response.content[:200]}...")
        print(f"[TIMER] Summarizer: {elapsed:.2f}s")
        print(f"=============================================\n")

        return {"summarized_result": response.content, "final_answer": response.content, "node_timings": {"summarizer": elapsed}}

    return summarizer_node


def create_general_answer_node():
    """创建 GENERAL ANSWER LLM 节点"""

    def general_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== GENERAL ANSWER NODE INPUT ==========")
        print(f"user_query: {state.get('user_query', '')}")
        print(f"rewritten_question: {state.get('rewritten_question', state.get('user_query', ''))}")
        print(f"===============================================\n")

        llm = get_llm()

        user_query = state.get("user_query", "")
        rewritten_question = state.get("rewritten_question", user_query)

        prompt = GENERAL_ANSWER_PROMPT.format(rewritten_question=rewritten_question)

        response = llm.invoke(prompt)

        # 防 LLM 原样复述模板占位符（曾输出"否，[简短依据]。两个名称……"模板原文）
        if "[简短依据]" in response.content or "<依据>" in response.content:
            corrective = (
                "\n\n【重要纠正】你上一次的回答原样输出了模板占位符（如[简短依据]）。"
                "必须把占位符替换为具体的判断依据文字，直接输出最终答案。"
            )
            response = llm.invoke(prompt + corrective)

        elapsed = time.time() - start_time

        print(f"\n========== GENERAL ANSWER NODE OUTPUT ==========")
        print(f"final_answer: {response.content[:200]}...")
        print(f"[TIMER] General Answer: {elapsed:.2f}s")
        print(f"===============================================\n")

        return {"final_answer": response.content, "node_timings": {"general_answer": elapsed}}

    return general_answer_node
