"""
LangGraph 状态定义
"""

from typing import TypedDict, Optional, List, Dict, Any


class QueryState(TypedDict):
    """Query State 标准结构"""
    version: int
    entity: Optional[Dict]
    metrics: List[Dict]
    dimensions: List[Dict]
    filters: List[Dict]
    time: Optional[Dict]
    ranking: Optional[Dict]
    comparison: Optional[Dict]
    extensions: Dict


class Clarification(TypedDict):
    """澄清状态"""
    type: str
    target: Dict
    question: str
    candidates: List[Dict]
    context: Dict
    status: str
    resolution: Dict


class GraphState(TypedDict):
    """LangGraph 全局状态"""
    
    # ==================== 输入 ====================
    user_id: str
    user_query: str
    previous_query_state: Optional[QueryState]
    previous_answer: str
    current_query_state_text: str
    
    # ==================== 意图理解 ====================
    rewritten_question: str
    relation: str
    operations: List[Dict]
    intent: str
    
    # ==================== Query State ====================
    query_state: QueryState
    validation_errors: List[str]
    query_state_status: str
    
    # ==================== 权限 ====================
    user_info: Dict
    user_roles: List[str]
    permissions: Dict
    field_permissions: Dict
    row_policies: List[Dict]
    user_scope: Optional[Dict]  # {scope_type, allowed_user_ids}
    
    # ==================== Schema ====================
    schema: Dict
    metadata: Dict
    
    # ==================== 语义 ====================
    semantic_result: Dict
    semantic_resolution_required: bool
    
    # ==================== SQL ====================
    query_plan: Dict
    sql_query_plan: Dict  # 格式化后的 SQL 查询计划
    sql: str
    validation_result: Dict
    
    # ==================== 安全 ====================
    security_result: Dict
    
    # ==================== 执行 ====================
    execution_result: Any
    normalized_result: List[Dict]
    validation_passed: bool
    
    # ==================== 值语义 ====================
    lookup_items: List[Dict]
    value_semantic_result: Dict
    
    # ==================== 澄清 ====================
    clarification: Optional[Clarification]
    pending_clarification: Optional[Dict]
    pending_clarification_required: bool
    clarification_answer: Optional[Dict]
    
    # ==================== 结果 ====================
    summarized_result: str
    final_answer: str
    
    # ==================== 状态 ====================
    status: str
    error: Optional[str]
    
    # ==================== 节点追踪 ====================
    node_timings: Dict[str, float]
    node_inputs: Dict[str, Any]
    node_outputs: Dict[str, Any]


def create_empty_query_state() -> QueryState:
    """创建空的 Query State"""
    return {
        "version": 3,
        "entity": None,
        "metrics": [],
        "dimensions": [],
        "filters": [],
        "time": None,
        "ranking": None,
        "comparison": None,
        "extensions": {}
    }


def create_initial_state() -> GraphState:
    """创建初始状态"""
    return {
        "user_id": "",
        "user_query": "",
        "previous_query_state": None,
        "previous_answer": "",
        "current_query_state_text": "{}",
        "rewritten_question": "",
        "relation": "",
        "operations": [],
        "intent": "",
        "query_state": create_empty_query_state(),
        "validation_errors": [],
        "query_state_status": "",
        "user_info": {},
        "user_roles": [],
        "permissions": {},
        "field_permissions": {},
        "row_policies": [],
        "user_scope": None,
        "schema": {},
        "metadata": {},
        "semantic_result": {},
        "semantic_resolution_required": False,
        "query_plan": {},
        "sql_query_plan": {},  # 格式化后的 SQL 查询计划
        "sql": "",
        "validation_result": {},
        "security_result": {},
        "execution_result": None,
        "normalized_result": [],
        "validation_passed": False,
        "lookup_items": [],
        "value_semantic_result": {},
        "clarification": None,
        "pending_clarification": None,
        "pending_clarification_required": False,
        "clarification_answer": None,
        "summarized_result": "",
        "final_answer": "",
        "status": "",
        "error": None,
        "node_timings": {},
        "node_inputs": {},
        "node_outputs": {}
    }
