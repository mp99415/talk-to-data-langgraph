"""
LangGraph 图组装
"""

import json
import time
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from .state import GraphState, create_initial_state

from .nodes.rewriter import create_rewriter_node, create_intent_analyzer_node
from .nodes.merger import create_merger_node
from .nodes.validator import create_query_state_validator_node, create_sql_validator_node, create_result_validator_node
from .nodes.schema import create_schema_builder_node
from .nodes.semantic import create_semantic_resolver_node
from .nodes.sql_gen import create_sql_generator_node, create_sql_executor_node
from .nodes.summarizer import create_result_summarizer_node, create_general_answer_node
from .nodes.clarification import create_clarification_generator_node, create_clarification_state_builder_node
from .nodes.user_info import create_user_info_node
from .nodes.user_roles import create_user_roles_node
from .nodes.permissions import create_rbac_permissions_node, create_field_permissions_node, create_row_policies_node
from .nodes.user_scope import create_user_scope_node
from .nodes.permission_resolver import create_permission_resolver_node
from .nodes.query_plan import create_query_plan_builder_node, create_query_plan_formatter_node
from .nodes.value_lookup import create_value_semantic_lookup_node, create_value_semantic_resolver_node
from .nodes.save_state import create_save_query_state_node, create_clear_pending_node, create_result_adapter_node, create_result_normalizer_node
from .nodes.current_date import create_get_current_date_node
from .nodes.sql_ast_parser import create_sql_ast_parser_node
from .nodes.permission_engine import create_permission_engine_node, create_authorized_sql_node
from .nodes.answer_validator import create_answer_validator_node
from .nodes.value_lookup_prep import create_value_lookup_prep_node
from .nodes.filter_value_resolver import create_filter_value_resolver_node
from .nodes.semantic_resolution_router import create_semantic_resolution_router_node
from .nodes.clarification_context_builder import create_semantic_clarification_context_builder_node, create_value_clarification_context_builder_node
from .nodes.schema_test_override import create_schema_test_override_node

from .edges.routers import (
    intent_router, query_state_router, sql_validator_router,
    semantic_resolution_router, result_validator_router, security_router,
    value_semantic_router, clarification_router
)
from .graph_helpers import build_unknown_field_message


def truncate_for_debug(value, max_length=200):
    """截断值用于调试输出"""
    if value is None:
        return "None"
    s = str(value)
    if len(s) > max_length:
        return s[:max_length] + "..."
    return s


def tracked_node(node_name: str, node_func):
    """包装节点函数，追踪执行时间和输入输出"""
    # 关键节点用更大的截断上限，便于排查（如 sub_query 配置、查询计划、SQL 生成）
    VERBOSE_NODES = {'rewriter', 'semantic_resolver', 'query_plan_builder',
                     'query_plan_formatter', 'sql_generator', 'sql_executor'}
    max_len = 2500 if node_name in VERBOSE_NODES else 200

    def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        print(f"\n========== {node_name.upper()} NODE ==========")
        print(f"Input keys: {list(state.keys())}")
        # 调试：检查 resolved_filters 是否在输入中
        if 'resolved_filters' in state:
            print(f"[DEBUG] resolved_filters in input: {len(state.get('resolved_filters', []))} items")
        print(f"===============================================\n")

        # 元数据字段列表（不记录到输入输出中）
        meta_keys = {'node_timings', 'node_inputs', 'node_outputs'}

        try:
            result = node_func(state)
            elapsed = time.time() - start_time

            # 调试：检查返回结果中是否有 resolved_filters
            if 'resolved_filters' in result:
                print(f"[DEBUG] {node_name}: returning resolved_filters with {len(result.get('resolved_filters', []))} items")

            # 过滤掉元数据字段，只记录业务数据
            filtered_state = {k: v for k, v in state.items() if k not in meta_keys}
            filtered_result = {k: v for k, v in result.items() if k not in meta_keys}
            
            # 调试：检查 filtered_result 中是否有 resolved_filters
            if 'resolved_filters' in filtered_result:
                print(f"[DEBUG] {node_name}: filtered_result contains resolved_filters with {len(filtered_result.get('resolved_filters', []))} items")
            elif 'resolved_filters' in result:
                print(f"[DEBUG] {node_name}: result has resolved_filters but filtered_result does not!")

            # 记录追踪信息
            result |= {
                "node_timings": {**state.get("node_timings", {}), node_name: elapsed},
                "node_inputs": {**state.get("node_inputs", {}), node_name: truncate_for_debug(filtered_state, max_len)},
                "node_outputs": {**state.get("node_outputs", {}), node_name: truncate_for_debug(filtered_result, max_len)},
            }

            print(f"\n========== {node_name.upper()} NODE OUTPUT ==========")
            print(f"Elapsed: {elapsed:.2f}s")
            print(f"Output keys: {list(result.keys())}")
            print(f"=================================================\n")

            return result
        except Exception as e:
            elapsed = time.time() - start_time

            # 过滤掉元数据字段
            filtered_state = {k: v for k, v in state.items() if k not in meta_keys}

            # 构建错误结果，合并之前的状态
            error_result = {
                "error": str(e),
                "node_timings": {**state.get("node_timings", {}), node_name: elapsed},
                "node_inputs": {**state.get("node_inputs", {}), node_name: truncate_for_debug(filtered_state, max_len)},
                "node_outputs": {**state.get("node_outputs", {}), node_name: f"ERROR: {str(e)[:100]}"},
            }

            print(f"\n========== {node_name.upper()} NODE ERROR ==========")
            print(f"Error: {str(e)}")
            print(f"Elapsed: {elapsed:.2f}s")
            print(f"=================================================\n")

            return error_result

    return wrapper


def create_graph() -> StateGraph:
    """创建 LangGraph"""

    workflow = StateGraph(GraphState)

    # ==================== 添加节点 ====================

    # 入口
    workflow.add_node("start", lambda state: state)

    # 用户信息
    workflow.add_node("get_user_info", tracked_node("get_user_info", create_user_info_node()))
    workflow.add_node("get_user_roles", tracked_node("get_user_roles", create_user_roles_node()))
    workflow.add_node("get_rbac_permissions", tracked_node("get_rbac_permissions", create_rbac_permissions_node()))
    workflow.add_node("get_field_permissions", tracked_node("get_field_permissions", create_field_permissions_node()))
    workflow.add_node("get_row_policies", tracked_node("get_row_policies", create_row_policies_node()))
    workflow.add_node("user_scope_calculator", tracked_node("user_scope_calculator", create_user_scope_node()))
    workflow.add_node("raw_authorization_normalizer", tracked_node("raw_authorization_normalizer", lambda state: state))
    workflow.add_node("permission_resolver", tracked_node("permission_resolver", create_permission_resolver_node()))

    # 意图理解
    workflow.add_node("rewriter", tracked_node("rewriter", create_rewriter_node()))
    workflow.add_node("intent_analyzer", tracked_node("intent_analyzer", create_intent_analyzer_node()))
    workflow.add_node("general_answer", tracked_node("general_answer", create_general_answer_node()))

    # Query State
    workflow.add_node("merger", tracked_node("merger", create_merger_node()))
    workflow.add_node("query_validator", tracked_node("query_validator", create_query_state_validator_node()))
    workflow.add_node("query_operation_normalizer", tracked_node("query_operation_normalizer", lambda state: state))

    # Schema
    workflow.add_node("schema_builder", tracked_node("schema_builder", create_schema_builder_node()))
    workflow.add_node("get_physical_columns", tracked_node("get_physical_columns", lambda state: state))
    workflow.add_node("get_physical_foreign_keys", tracked_node("get_physical_foreign_keys", lambda state: state))
    workflow.add_node("get_business_metadata", tracked_node("get_business_metadata", lambda state: state))

    # 语义
    workflow.add_node("semantic_resolver", tracked_node("semantic_resolver", create_semantic_resolver_node()))
    workflow.add_node("semantic_resolution_guard", tracked_node("semantic_resolution_guard", lambda state: state))
    workflow.add_node("semantic_resolution_router", tracked_node("semantic_resolution_router", create_semantic_resolution_router_node()))
    workflow.add_node("semantic_clarification_context_builder", tracked_node("semantic_clarification_context_builder", create_semantic_clarification_context_builder_node()))
    workflow.add_node("value_clarification_context_builder", tracked_node("value_clarification_context_builder", create_value_clarification_context_builder_node()))

    # 查询计划
    workflow.add_node("query_plan_builder", tracked_node("query_plan_builder", create_query_plan_builder_node()))
    workflow.add_node("query_plan_formatter", tracked_node("query_plan_formatter", create_query_plan_formatter_node()))
    workflow.add_node("get_current_date", tracked_node("get_current_date", create_get_current_date_node()))
    workflow.add_node("schema_test_override", tracked_node("schema_test_override", create_schema_test_override_node()))

    # 值语义解析
    workflow.add_node("value_semantic_lookup", tracked_node("value_semantic_lookup", create_value_semantic_lookup_node()))
    workflow.add_node("value_semantic_resolver", tracked_node("value_semantic_resolver", create_value_semantic_resolver_node()))
    workflow.add_node("value_lookup_prep", tracked_node("value_lookup_prep", create_value_lookup_prep_node()))
    workflow.add_node("filter_value_resolver", tracked_node("filter_value_resolver", create_filter_value_resolver_node()))

    # SQL
    workflow.add_node("sql_generator", tracked_node("sql_generator", create_sql_generator_node()))
    workflow.add_node("sql_validator", tracked_node("sql_validator", create_sql_validator_node()))
    workflow.add_node("sql_ast_parser", tracked_node("sql_ast_parser", create_sql_ast_parser_node()))
    workflow.add_node("permission_engine", tracked_node("permission_engine", create_permission_engine_node()))
    workflow.add_node("authorized_sql", tracked_node("authorized_sql", create_authorized_sql_node()))
    workflow.add_node("sql_executor", tracked_node("sql_executor", create_sql_executor_node()))

    # 安全验证：尊重上游 permission_engine 的判定，只在缺失时默认 True
    def _security_validator_node(state):
        cur = state.get("security_result") or {}
        if "allowed" in cur:
            return {"security_result": cur}
        return {"security_result": {"allowed": True}}
    workflow.add_node("security_validator", tracked_node("security_validator", _security_validator_node))

    # 结果
    workflow.add_node("result_summarizer", tracked_node("result_summarizer", create_result_summarizer_node()))
    workflow.add_node("result_validator", tracked_node("result_validator", create_result_validator_node()))
    workflow.add_node("result_adapter", tracked_node("result_adapter", create_result_adapter_node()))
    workflow.add_node("result_normalizer", tracked_node("result_normalizer", create_result_normalizer_node()))

    # 澄清
    workflow.add_node("clarification_generator", tracked_node("clarification_generator", create_clarification_generator_node()))
    workflow.add_node("clarification_builder", tracked_node("clarification_builder", create_clarification_state_builder_node()))
    workflow.add_node("clarification_answer_handler", tracked_node("clarification_answer_handler", lambda state: state))
    workflow.add_node("answer_validator", tracked_node("answer_validator", create_answer_validator_node()))

    # 状态保存
    workflow.add_node("save_query_state", tracked_node("save_query_state", create_save_query_state_node()))
    workflow.add_node("clear_pending", tracked_node("clear_pending", create_clear_pending_node()))

    # 输出
    workflow.add_node("final_answer", tracked_node("final_answer", lambda state: {"final_answer": state.get("summarized_result", "") or state.get("final_answer", "")}))
    
    # error_answer 节点：处理错误和空结果

    def error_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
        error = state.get('error')
        validation_passed = state.get('validation_passed', True)
        execution_result = state.get('execution_result', [])
        validation_result = state.get('validation_result', {})
        schema = state.get('schema', {}) or {}
        user_query = state.get('user_query', '') or state.get('rewritten_question', '')

        # ========== 统一 UNKNOWN_FIELD 错误处理 ==========
        # 如果 SQL Validator 检测到字段不存在警告 → 给出统一格式的友好提示
        warnings = validation_result.get('warnings', []) or []
        for w in warnings:
            if w.get('type') == 'UNKNOWN_FIELD':
                field = w.get('field', '')
                final_answer = build_unknown_field_message(
                    field=field, user_query=user_query, schema=schema
                )
                return {"final_answer": final_answer}

        # 如果是空结果（validation_passed=False 但没有 error），返回友好提示
        if not validation_passed and not error:
            # 检查是否为空结果
            if not execution_result or len(execution_result) == 0:
                return {"final_answer": "抱歉，根据查询结果，当前系统中没有找到符合条件的记录。"}
            return {"final_answer": f"抱歉，查询结果为空（validation_passed={validation_passed}）。"}

        # 正常的错误处理
        if error:
            return {"final_answer": f"错误: {error}"}
        return {"final_answer": "未知错误，请重试。"}
    
    workflow.add_node("error_answer", tracked_node("error_answer", error_answer_node))
    workflow.add_node("unsafe_answer", tracked_node("unsafe_answer", lambda state: {"final_answer": "当前请求涉及数据库写入或危险操作，不允许执行。"}))
    workflow.add_node("semantic_error_answer", tracked_node("semantic_error_answer", lambda state: {"final_answer": "语义解析失败，请重试。"}))
    workflow.add_node("permission_error_answer", tracked_node("permission_error_answer", lambda state: {"final_answer": "您没有权限执行此查询。"}))

    # ==================== 添加边 ====================

    # 入口
    workflow.add_edge(START, "start")
    workflow.add_edge("start", "get_user_info")

    # 用户信息流程
    workflow.add_edge("get_user_info", "get_user_roles")
    workflow.add_edge("get_user_roles", "get_rbac_permissions")
    workflow.add_edge("get_rbac_permissions", "get_field_permissions")
    workflow.add_edge("get_field_permissions", "get_row_policies")
    workflow.add_edge("get_row_policies", "user_scope_calculator")
    workflow.add_edge("user_scope_calculator", "raw_authorization_normalizer")
    workflow.add_edge("raw_authorization_normalizer", "permission_resolver")
    workflow.add_edge("permission_resolver", "rewriter")

    # 意图理解
    workflow.add_edge("rewriter", "intent_analyzer")

    workflow.add_conditional_edges(
        "intent_analyzer",
        intent_router,
        {
            "query": "merger",
            "general": "general_answer",
            "unsafe": "unsafe_answer"
        }
    )

    workflow.add_edge("general_answer", "final_answer")
    workflow.add_edge("unsafe_answer", "final_answer")

    # Query State
    workflow.add_edge("merger", "query_validator")

    workflow.add_conditional_edges(
        "query_validator",
        query_state_router,
        {
            "continue": "schema_builder",
            "error": "error_answer",
            "ambiguous": "clarification_generator"
        }
    )

    # Schema
    workflow.add_edge("schema_builder", "get_physical_columns")
    workflow.add_edge("get_physical_columns", "get_physical_foreign_keys")
    workflow.add_edge("get_physical_foreign_keys", "get_business_metadata")
    workflow.add_edge("get_business_metadata", "semantic_resolver")

    # 语义路由 - semantic_resolver -> semantic_resolution_router
    workflow.add_conditional_edges(
        "semantic_resolver",
        semantic_resolution_router,
        {
            "continue": "semantic_resolution_router",
            "clarification": "semantic_resolution_router"
        }
    )

    # semantic_resolution_router 输出路由
    workflow.add_conditional_edges(
        "semantic_resolution_router",
        lambda x: x.get("semantic_resolution_route", "error"),
        {
            "continue": "filter_value_resolver",
            "clarification": "clarification_generator",
            "error": "error_answer"
        }
    )

    # Filter Value Resolver - 解析 business_value -> physical_value
    workflow.add_edge("filter_value_resolver", "query_plan_builder")

    # 查询计划
    workflow.add_edge("query_plan_builder", "query_plan_formatter")
    workflow.add_edge("query_plan_formatter", "sql_generator")

    # 值语义解析（可选流程）
    workflow.add_edge("value_semantic_lookup", "value_semantic_resolver")
    workflow.add_edge("value_semantic_resolver", "query_plan_builder")

    # SQL - 经 Permission Engine 应用 row policy 后再进入验证
    workflow.add_edge("sql_generator", "permission_engine")
    workflow.add_edge("permission_engine", "authorized_sql")
    workflow.add_edge("authorized_sql", "sql_validator")

    workflow.add_conditional_edges(
        "sql_validator",
        sql_validator_router,
        {
            "valid": "security_validator",
            "invalid": "error_answer"
        }
    )

    # 安全验证
    workflow.add_conditional_edges(
        "security_validator",
        security_router,
        {
            "allowed": "sql_executor",
            "forbidden": "permission_error_answer"
        }
    )

    # 执行
    workflow.add_edge("sql_executor", "result_adapter")
    workflow.add_edge("result_adapter", "result_normalizer")
    workflow.add_edge("result_normalizer", "result_validator")

    workflow.add_conditional_edges(
        "result_validator",
        result_validator_router,
        {
            "valid": "result_summarizer",
            "invalid": "error_answer"
        }
    )

    # 结果
    workflow.add_edge("result_summarizer", "save_query_state")
    workflow.add_edge("save_query_state", "final_answer")

    # 澄清流程
    workflow.add_edge("clarification_generator", "clarification_builder")
    workflow.add_edge("clarification_builder", "merger")

    # 清除待处理
    workflow.add_edge("clarification_answer_handler", "clear_pending")
    workflow.add_edge("clear_pending", "merger")

    # 最终
    workflow.add_edge("final_answer", END)
    workflow.add_edge("error_answer", END)
    workflow.add_edge("permission_error_answer", END)
    workflow.add_edge("semantic_error_answer", END)
    workflow.add_edge("unsafe_answer", END)

    return workflow.compile()


def run_graph(
    user_id: str,
    user_query: str,
    previous_query_state: dict = None,
    previous_answer: str = None
) -> Dict[str, Any]:
    """
    运行 LangGraph

    Args:
        user_id: 用户 ID
        user_query: 用户问题
        previous_query_state: 上一轮 Query State
        previous_answer: 上一轮最终回答（用于解析"它/那家公司"等指代和省略式追问）

    Returns:
        最终结果
    """
    graph = create_graph()

    initial_state = create_initial_state()
    initial_state["user_id"] = user_id
    initial_state["user_query"] = user_query
    initial_state["previous_query_state"] = previous_query_state or {}
    initial_state["previous_answer"] = previous_answer or ""

    if previous_query_state:
        initial_state["current_query_state_text"] = json.dumps(previous_query_state, ensure_ascii=False)

    result = graph.invoke(initial_state)

    # 获取最终答案
    final_answer = result.get("final_answer") or result.get("summarized_result", "")

    return {
        "answer": final_answer,
        "final_answer": final_answer,
        "summarized_result": result.get("summarized_result", ""),
        "query_state": result.get("query_state", {}),
        "sql": result.get("sql", ""),
        "status": "SUCCESS" if final_answer else "FAILED",
        "row_policy_applied": result.get("row_policy_applied", False),
        "node_timings": result.get("node_timings", {}),
        "node_inputs": result.get("node_inputs", {}),
        "node_outputs": result.get("node_outputs", {})
    }
