# Talk-to-Data 主流化升级方案说明书

> 版本：V1.0  
> 日期：2026-09-27  
> 配套文档：[Talk_to_Data_Agent_Harness_升级架构方案说明书.md](./Talk_to_Data_Agent_Harness_升级架构方案说明书.md)  
> 目标：基于原方案的核心思想，重新规划**符合业界主流方向**的升级路径，避免重新造轮子。

---

## 一、原方案核心思想（保留）

原 Agent Harness 升级方案提出了 5 个**正确的核心思想**，本方案全部继承：

1. **职责正交分离**：Agent ≠ Security ≠ Compiler ≠ Semantic
2. **DSL 降 LLM 幻觉**：不让 LLM 直接产 SQL，让 LLM 产语义 DSL，由确定性内核渲染 SQL
3. **Security Kernel 独立**：所有 SQL 必须经过 AST + RBAC + Row/Field Permission
4. **HITL 强制介入高风险操作**：大规模导出、敏感字段、跨部门数据
5. **Observability 全链路 Trace**：可解释、可回放、可审计

---

## 二、为什么需要"主流化"重写

原方案的实施路径与业界主流方向相反：

| 维度 | 原方案做法 | 业界主流方向 |
|---|---|---|
| 编排层 | 自研 Agent Harness | **LangGraph 1.0 subgraph** |
| 语义层 | 自研 Entity/Metric/Dimension | **dbt MetricFlow / Cube.js** |
| SQL 引擎 | 自研 Query Compiler | **SQLGlot / Apache Calcite** |
| Trace / Eval | 自研 Trace | **LangSmith / LangFuse / OpenLLMetry** |
| HITL | 自研 HITL Manager | **LangGraph `interrupt`** |
| Memory | 自研三层 Memory | **LangGraph Store + Postgres** |
| Policy | 自研 Policy Guard | **OPA / Cerbos** |
| Tool 粒度 | 细粒度（每节点一个 Tool） | **粗粒度（一类业务一个 Tool）** |
| Runtime | 自研 Runtime（Phase 7） | **不需要，单进程 + K8s** |

**结果**：原方案需要 30-50 FTE × 12 月，主流化方案只需 5-8 FTE × 12 月。

---

## 三、整体路线图（4 阶段，12-18 个月）

```
Phase 1 (1-2 月): 观测 + 节点 Instrument     ← 零业务改动，立即可做
Phase 2 (3-4 月): DSL 中间表示 + Query Compiler ← 核心收益（降 LLM 幻觉）
Phase 3 (4-6 月): Agent Harness Subgraph      ← 复杂分析能力
Phase 4 (6-12 月): 多模态 + Federation        ← 长期演进
```

**关键原则**：

> 保留 LangGraph 做编排，让 LangGraph 自己当 Harness；引入成熟框架做语义/编译/观测；DSL 仅作为 LangGraph 节点内的中间表示。

---

# 四、Phase 1：观测 + 节点 Instrument（1-2 月）

## 4.1 目标

零业务逻辑改动，加 trace + eval + 节点级安全 policy。

## 4.2 主流工具栈

| 能力 | 选型 | 替代（非主流） |
|---|---|---|
| Trace | LangSmith / LangFuse / Arize Phoenix | 自研 Trace DB |
| Eval | LangSmith Evaluations / DeepEval / Ragas | 自研 scoring |
| LLM Token 监控 | OpenLLMetry (OTel) / LangSmith | 自研 token counter |
| 节点 Policy | OPA (Open Policy Agent) / Cerbos | 自研 Policy Guard |
| Metrics Dashboard | Grafana + Prometheus | 自研 dashboard |

## 4.3 落地步骤

### Step 1 (Week 1-2)：接 LangFuse（开源，可自托管）

```python
# 主流模式：在 LangGraph 节点外包装 trace，不改业务代码
from langfuse.decorators import observe, langfuse_context

@observe(name="sql_generator")
def sql_generator_node(state: dict) -> dict:
    # 业务逻辑保持不变
    llm = get_llm()
    sql = llm.invoke(...)
    # trace 自动记录 input/output/latency/token
    return {"sql": sql}
```

**收益**：

- 自动记录每个节点的 input/output/latency/token/cost
- 90% 失败 case 可在 LangFuse UI 一键定位

### Step 2 (Week 3-4)：接入 regression_test_cases.csv 自动评估

```python
# 用 SQLGlot parse + AST compare 自动 diff
import sqlglot
from sqlglot import exp

def evaluate_sql_match(actual: str, expected: str) -> float:
    """基于 AST 的 SQL 相似度评分"""
    try:
        ast_actual = sqlglot.parse_one(actual)
        ast_expected = sqlglot.parse_one(expected)
        # 比较 AST 结构而非字符串
        return 1.0 if ast_actual.sql() == ast_expected.sql() else 0.0
    except Exception:
        return 0.0
```

### Step 3 (Week 5-6)：节点 Policy Guard（OPA）

```rego
# policy/sql_executor.rego
package node_policy

default allow = false

allow {
    # sql_executor 必须有 permission_result.authorized=true
    input.permission_result.authorized == true
    # sql_executor 必须经过 ast_parser
    input.sql_ast != null
    # 单次查询不超过 60 秒
    input.elapsed_seconds < 60
}

allow {
    # HITL 已审批的大规模导出
    input.hitl_decision == "approved"
    input.query_dsl.estimated_rows > 100000
}
```

### Step 4 (Week 7-8)：Grafana Dashboard

```
Grafana 看板:
- 88 case P50/P95 延迟
- LLM token 消耗 / 单 case 成本
- 权限拦截率 / 失败率
- 节点级错误率 Top 5
```

## 4.4 收益

| 指标 | 当前 | Phase 1 后 |
|---|---|---|
| 失败 case 定位时间 | ~30 分钟（人工翻 log） | **< 1 分钟**（LangFuse 一键定位） |
| 性能瓶颈识别 | 凭经验 | **Grafana 自动 Top 5** |
| 危险操作拦截 | 无 | **OPA 强制拦截** |
| Token 成本可见性 | 无 | **全链路统计** |

---

# 五、Phase 2：DSL 中间表示 + Query Compiler（3-4 月）

## 5.1 目标

将 LLM 幻觉导致的 SQL 错误从 ~30% 降到 < 5%。**简单查询不再调用 LLM**，直接确定性渲染。

## 5.2 主流工具栈

| 能力 | 选型 | 原方案做法（非主流） |
|---|---|---|
| 语义建模 | **dbt Semantic Layer (MetricFlow)** 或 **Cube.js** | 自研 Entity/Metric/Dimension |
| SQL Parser/Generator | **SQLGlot**（Python 轻量级） | 自研 Query Compiler |
| SQL 优化 | **SQLGlot Optimizer** | 无 |
| DSL Schema 校验 | Pydantic + JSON Schema | 自研 |
| LLM 输出结构化 | **OpenAI Structured Outputs** / **Instructor** | prompt 工程 |

## 5.3 落地策略：双轨并行（关键）

```
Track A: 简单查询（~60%）走 Query DSL + 确定性渲染
Track B: 复杂查询（~40%）继续走 LLM SQL Generator + 增强保护

双轨并行 3 个月：
- Track A 的 SQL 跟原 SQL 自动 diff
- Track A 通过率 > 90% 后逐步扩大比例
- Track B 保留 LLM fallback
```

## 5.4 Track A 实施步骤

### Step 1 (Month 1)：引入 SQLGlot + 定义 DSL Schema

```python
# 主流模式：复用现有 sql_query_plan 作为初始 DSL
from pydantic import BaseModel, Field
from typing import List, Literal
import sqlglot
from sqlglot import exp

class Metric(BaseModel):
    name: str  # "销售额"
    table: str  # "orders"
    field: str  # "amount"
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"] = "SUM"

class Dimension(BaseModel):
    name: str  # "地区"
    table: str  # "orders"
    field: str  # "region"

class TimeRange(BaseModel):
    field: str  # "order_date"
    start: str  # "2026-01-01"
    end: str    # "2027-01-01"

class Filter(BaseModel):
    table: str
    field: str
    operator: Literal["=", "!=", "<", ">", "IN"] = "="
    value: str

class QueryDSL(BaseModel):
    """业务查询 DSL：只描述"做什么"，不描述"怎么做 SQL" """
    grain: Literal["SCALAR", "GROUPED", "DETAIL", "RANKING"] = "SCALAR"
    main_table: str = "orders"
    metrics: List[Metric] = []
    dimensions: List[Dimension] = []
    filters: List[Filter] = []
    time: TimeRange | None = None
    limit: int | None = None
```

### Step 2 (Month 2)：DSL → SQL 确定性渲染器

```python
class QueryCompiler:
    """DSL → SQL 确定性渲染，零 LLM 参与"""

    def compile(self, dsl: QueryDSL) -> str:
        # 1. DSL Validation
        dsl.validate()

        # 2. Logical Plan（生成 AST-like 结构）
        select_fields = []
        group_by_fields = []

        for m in dsl.metrics:
            select_fields.append(f"{m.aggregation}(`{m.table}`.`{m.field}`) AS `{m.name}`")
        for d in dsl.dimensions:
            select_fields.append(f"`{d.table}`.`{d.field}` AS `{d.name}`")
            group_by_fields.append(f"`{d.table}`.`{d.field}`")

        # 3. WHERE 条件
        where_parts = []
        for f in dsl.filters:
            where_parts.append(f"`{f.table}`.`{f.field}` {f.operator} '{f.value}'")
        if dsl.time:
            where_parts.append(f"`{dsl.time.field}` >= '{dsl.time.start}'")
            where_parts.append(f"`{dsl.time.field}` < '{dsl.time.end}'")

        # 4. SQL 模板渲染
        sql = f"SELECT {', '.join(select_fields)} FROM `{dsl.main_table}`"
        if where_parts:
            sql += f" WHERE {' AND '.join(where_parts)}"
        if group_by_fields:
            sql += f" GROUP BY {', '.join(group_by_fields)}"
        if dsl.limit:
            sql += f" LIMIT {dsl.limit}"

        # 5. SQLGlot 标准化（format + parse 验证）
        return sqlglot.transpile(sql, read='mysql', write='mysql')[0]
```

### Step 3 (Month 3)：LLM 输出 DSL（而非 SQL）

```python
# 主流模式：Instructor + Pydantic 强类型校验
import instructor
from openai import OpenAI

client = instructor.from_openai(OpenAI())

def parse_query_to_dsl(user_query: str, semantic_layer: dict) -> QueryDSL:
    """LLM 输出强类型 DSL"""
    response = client.chat.completions.create(
        model="gpt-4",
        response_model=QueryDSL,  # Pydantic 强类型
        messages=[
            {"role": "system", "content": f"你是查询解析助手，输出 JSON DSL。语义层：{semantic_layer}"},
            {"role": "user", "content": user_query},
        ],
        max_retries=2,  # 校验失败自动 retry 1 次
    )
    return response
```

**对比原方案（Document 第十八章）**：

```
原方案：LLM 输出 DSL → DSL → Compiler → SQL（没说 DSL 怎么校验）
主流化：LLM 输出 DSL → Pydantic 校验 → DSL → 模板渲染 → SQL（结构化保证）
```

### Step 4 (Month 4)：切换比例 60% → 80% → 95%

```
Track A 切换策略:
- Week 1-2: 10% case 走 Track A（监控延迟 / 成功率）
- Week 3-4: 50% case 走 Track A
- Week 5-6: 80% case 走 Track A
- Week 7-8: 95% case 走 Track A（5% 失败自动回退到 Track B）

监控指标:
- Track A 通过率 > 90%（不达标则暂停切换）
- Track A 延迟 < Track A 原方案
- regression_test_cases.csv 不退化
```

## 5.5 Track B 增强保护（保留 LLM 但加防护）

```python
def sql_generator_with_protection(state):
    # 保留 LLM 生成 SQL
    sql = llm.invoke(...)

    # SQLGlot parse → AST 验证
    try:
        parsed = sqlglot.parse_one(sql)
    except Exception as e:
        raise SqlSyntaxError(f"LLM 输出非法 SQL: {e}")

    # 检测危险 SQL（无 WHERE / DROP / DELETE）
    dangerous = detect_dangerous_sql(parsed)
    if dangerous:
        raise DangerousSqlError(dangerous)

    # 检测 GROUP BY 缺失
    if has_aggregation_without_groupby(parsed):
        sql = auto_add_groupby(parsed)

    return {"sql": sql.sql()}
```

## 5.6 收益

| 指标 | 当前 | Phase 2 后 |
|---|---|---|
| LLM 幻觉率 | ~30% | **< 5%**（简单查询不再调 LLM） |
| SQL 执行错误率 | ~15% | **< 3%** |
| 单 case 成本 | $0.05-0.20 | **$0.02-0.08**（简单查询零 LLM） |
| 88-case 通过率 | ~85% | **> 95%** |

---

# 六、Phase 3：Agent Harness Subgraph（4-6 月）

## 6.1 目标

让 Agent 能**动态拆解复杂分析任务**（同比 / 下钻 / 异常归因），HITL 无缝集成。

## 6.2 主流工具栈

| 能力 | 选型 | 原方案做法（非主流） |
|---|---|---|
| 动态编排 | **LangGraph 1.0 subgraph + interrupt** | 自研 Agent Runtime |
| Multi-Agent | **LangGraph Multi-Agent Supervisor** | 自研 Supervisor |
| Tool Registry | **LangGraph ToolNode + Function Calling** | 自研 Tool Registry |
| HITL | **LangGraph `interrupt_before` / `interrupt_after`** | 自研 HITL Manager |
| State 管理 | LangGraph Checkpointer + Thread | 自研 State Manager |
| Memory | **LangGraph Store + Postgres Backend** | 自研三层 Memory |

## 6.3 关键决策：保留 LangGraph，让 subgraph 当 Harness

**核心原则**：

> LangGraph 1.0 已经原生支持 subgraph（动态决策）、interrupt（HITL）、checkpointing（时间旅行 debug）、Store（Memory）、ToolNode（Tool Registry）。文档要的 Harness 80% LangGraph 已经做了，**不要再造一遍**。

### 主流模式示例

```python
from langgraph.graph import StateGraph, START, END

# 子图: Agent Harness（动态决策层）
class AgentState(TypedDict):
    user_query: str
    plan: List[str]
    step: int
    max_steps: int
    tool_results: List[dict]

agent_subgraph = StateGraph(AgentState)

agent_subgraph.add_node("understand", understand_node)  # LLM 理解任务
agent_subgraph.add_node("plan", plan_node)              # LLM 选 Tool + 顺序
agent_subgraph.add_node("tool_executor", tool_executor_node)  # 执行 Tool
agent_subgraph.add_node("reflect", reflect_node)        # 评估是否需要更多步骤

agent_subgraph.add_edge(START, "understand")
agent_subgraph.add_edge("understand", "plan")
agent_subgraph.add_edge("plan", "tool_executor")
agent_subgraph.add_edge("tool_executor", "reflect")

# 条件边: 继续 or 结束
agent_subgraph.add_conditional_edges(
    "reflect",
    lambda s: "continue" if s["step"] < s["max_steps"] else "end",
    {"continue": "plan", "end": END}
)

# 主图: 把子图当一个节点
main_graph = StateGraph(GraphState)
main_graph.add_node("agent_harness", agent_subgraph.compile())
main_graph.add_edge("query_validator", "agent_harness")
main_graph.add_edge("agent_harness", "security_kernel")
```

## 6.4 Tool Registry（粗粒度）

**主流原则**：Tool 是"完成一类业务"，**不是"一个 pipeline 节点"**。

```python
from langchain_core.tools import tool

@tool
def execute_business_query(user_id: str, query_dsl: QueryDSL) -> QueryResult:
    """
    业务查询工具（粗粒度，一类业务一个 Tool）：
      - 内部调 DSL → SQL 渲染
      - 走 Permission Engine
      - 执行 SQL
      - 返回结构化结果
    """
    pass

@tool
def compare_periods(
    user_id: str,
    current_dsl: QueryDSL,
    previous_dsl: QueryDSL
) -> ComparisonResult:
    """对比两个时间段的指标（如同比、环比）"""
    pass

@tool
def drill_down(
    user_id: str,
    parent_dsl: QueryDSL,
    breakdown_dim: str
) -> DetailResult:
    """下钻分析（按维度拆分）"""
    pass

@tool
def explain_anomaly(
    user_id: str,
    anomaly_dsl: QueryDSL,
    threshold: float
) -> InsightResult:
    """异常归因（找出下降 / 上升原因）"""
    pass
```

**对比原方案（Document 第七章）**：

```
原方案：query_state.read / query_state.update / query_dsl.build / query.compile
       （细粒度，每个节点一个 Tool）

主流化：execute_business_query / compare_periods / drill_down
       （粗粒度，一类业务一个 Tool，LLM 决策负担低）
```

## 6.5 HITL 用 LangGraph 原生 interrupt

```python
from langgraph.graph import interrupt

def sensitive_query_node(state):
    """敏感查询节点：超大规模导出需要 HITL"""
    # 1. 检测是否需要 HITL
    if state["query_dsl"].estimated_rows > 100000:
        # interrupt 会暂停 graph + 持久化 state
        # 等人工 approve 后从 checkpointer 恢复
        decision = interrupt({
            "type": "approval_required",
            "reason": "large_data_export",
            "estimated_rows": 100000,
            "preview": state["query_dsl"].preview()
        })
        if decision != "approved":
            return {"status": "DENIED", "reason": "human_rejected"}

    # 2. 继续执行
    return execute_query(state)
```

**主流优势**：

- HITL 状态由 LangGraph Checkpointer 自动持久化
- 崩溃恢复：从上次 interrupt 状态继续执行
- 多轮对话：同一个 thread_id 恢复对话上下文

## 6.6 Memory 用 LangGraph Store

```python
from langgraph.store.memory import InMemoryStore
from langgraph.graph import StateGraph

# 主流模式：LangGraph Store + Postgres 后端
store = InMemoryStore()  # 生产换 PostgresStore

# 三层 Memory 设计：
# - Conversation Memory: store.put(namespace=("conversation", user_id), key=msg_id, value=msg)
# - Query State Memory: store.put(namespace=("query_state", user_id), key=query_id, value=state)
# - Task Memory: state["task_id"] 自动管理（不需要外部存储）
```

## 6.7 收益

| 能力 | Phase 2 后 | Phase 3 后 |
|---|---|---|
| 同比 / 环比分析 | ❌ 需手工拆解 | ✅ 自动 Tool 调用 |
| 下钻分析 | ❌ 需手工拆解 | ✅ 自动 Tool 调用 |
| 异常归因 | ❌ 需手工拆解 | ✅ 自动 Tool 调用 |
| 大规模导出 HITL | ❌ 无拦截 | ✅ 强制人工审批 |
| 多轮对话恢复 | ❌ 部分支持 | ✅ LangGraph Checkpointer 原生支持 |

---

# 七、Phase 4：多模态 + Federation（6-12 月，长期）

## 7.1 目标

从单 SQL → DAX / KQL / API / Vector 联邦查询。

## 7.2 主流工具栈

| 能力 | 选型 |
|---|---|
| 多方言 SQL | **SQLGlot transpiler**（Python 原生，20+ 方言） |
| OLAP / Vector | Cube.js Federation / StarRocks / Doris |
| GraphQL 联邦 | Apollo Federation / Hasura |
| Real-time | Materialize / Flink SQL |
| Document DB | MongoDB Atlas SQL Interface / FerretDB |

## 7.3 关键决策：用 SQLGlot 做方言适配

```python
import sqlglot

# MySQL → ClickHouse
sql = "SELECT amount FROM orders LIMIT 10"
clickhouse_sql = sqlglot.transpile(sql, read='mysql', write='clickhouse')[0]

# MySQL → Spark SQL
spark_sql = sqlglot.transpile(sql, read='mysql', write='spark')[0]

# MySQL → PostgreSQL（带方言适配）
pg_sql = sqlglot.transpile(sql, read='mysql', write='postgres')[0]
```

## 7.4 不自研 DAX / KQL 引擎

- **DAX**：微软有 Analysis Services，外部集成用 TOM/XMLA 协议
- **KQL**：Azure Data Explorer 有官方 SDK
- 自研 DAX/KQL 引擎是 50+ FTE 项目，**不值得**

## 7.5 Federation 模式

```python
# 主流模式：Cube.js Federation
# - 一个 Semantic Layer 描述多个数据源
# - Agent 查询时自动路由到对应数据源
# - 跨源 JOIN 由 Cube.js 处理

@cube_model
class Orders:
    sql_table = "mysql.orders"
    # ...

@cube_model  
class Customers:
    sql_table = "mongo.customers"
    # ...

# Agent 跨源查询："订单 + 客户信息"
# Cube.js 自动: SELECT o.*, c.name FROM orders o JOIN customers c
```

---

# 八、与原方案对比

| 维度 | 原方案 | 主流化路径 |
|---|---|---|
| 编排层 | 自研 Agent Harness | **LangGraph 1.0 subgraph** |
| 语义层 | 自研 Entity/Metric/Dimension | **dbt MetricFlow / Cube.js** |
| SQL 引擎 | 自研 Query Compiler | **SQLGlot + 模板渲染** |
| Trace | 自研 Trace | **LangFuse + OpenTelemetry** |
| HITL | 自研 HITL Manager | **LangGraph interrupt** |
| Memory | 自研三层 Memory | **LangGraph Store + Postgres** |
| Policy | 自研 Policy Guard | **OPA / Cerbos** |
| Tool 粒度 | 细粒度（每节点一个 Tool） | **粗粒度（一类业务一个 Tool）** |
| Runtime | 自研 Runtime（Phase 7） | **不需要，单进程 + K8s** |
| 周期 | Phase 0-7（37 章节） | **Phase 1-4（4 阶段）** |
| 工作量 | 估计 30-50 FTE × 12 月 | **估计 5-8 FTE × 12 月** |

---

# 九、给团队的 3 条执行原则

## 原则 1：保留 LangGraph，让 LangGraph 自己当 Harness

LangGraph 1.0 已经原生支持：
- subgraph（动态决策）
- interrupt（HITL）
- checkpointing（时间旅行 debug）
- Store（Memory）
- ToolNode（Tool Registry）

原方案要的 Harness 80% LangGraph 已经做了。**不要再造一遍**。

## 原则 2：在节点外加 Harness，不在节点内重写

```python
# 主流模式：在 LangGraph 节点外包装 Harness
from functools import wraps

def with_harness(node_fn):
    """Harness 装饰器：给 LangGraph 节点加 trace + policy + budget"""
    @wraps(node_fn)
    def wrapper(state):
        # 1. Trace
        with tracer.start_as_current_span(node_fn.__name__) as span:
            # 2. Policy Guard
            policy_check(node_fn.__name__, state)
            # 3. Budget Guard
            if token_budget_exceeded():
                raise BudgetExceeded
            # 4. 执行原节点（不改业务逻辑）
            result = node_fn(state)
            # 5. Eval / 记录
            span.set_attribute("output", result)
            return result
    return wrapper

# 用法：原有节点加一行装饰器
@with_harness
def sql_generator_node(state):
    ...  # 业务逻辑完全不变
```

## 原则 3：DSL 是节点内的中间表示，不是跨服务的协议

```python
# 主流做法：DSL 是 LangGraph state 的一部分
class GraphState(TypedDict):
    user_query: str
    query_state: dict         # 业务语义
    query_dsl: QueryDSL | None  # DSL 中间表示（不是协议）
    sql: str
    authorized_sql: str

# DSL 在 sql_generator 节点内生成
# 在 permission_engine 节点内消费
# 不暴露成跨服务 API（避免 RPC 复杂度）
```

---

# 十、4 阶段时间表 + 风险 + 成功标准

| Phase | 时长 | 风险 | 成功标准 | 关键依赖 |
|---|---|---|---|---|
| **Phase 1** | 1-2 月 | 低 | Trace 覆盖率 100% / 88 case 自动 eval / Policy guard 5 条规则上线 | LangFuse 部署 / OPA 集成 |
| **Phase 2** | 3-4 月 | 中 | Track A 简单查询通过率 > 90% / 简单查询不再调 LLM / 88 case 0 退化 | SQLGlot 学习 / DSL schema 设计 / 双轨机制 |
| **Phase 3** | 4-6 月 | 中高 | 复杂分析（同比 / 下钻 / 异常归因）100% 覆盖 / HITL SLA < 5min | LangGraph 1.0 subgraph / Tool 设计 / LangGraph Store |
| **Phase 4** | 6-12 月 | 中 | 多方言 SQL 转译 / Cube.js Federation 试点 / DAX/KQL 集成 | SQLGlot transpiler / Cube.js / Azure SDK |

---

# 十一、预期收益总结

## 11.1 投入对比

| 维度 | 原方案 | 主流化方案 |
|---|---|---|
| 工作量 | 30-50 FTE × 12 月 | **5-8 FTE × 12 月** |
| 风险等级 | 高（断崖式 7 阶段） | **低（渐进 4 阶段）** |
| 失败回滚 | 无 | **每阶段可独立回滚** |
| 工具栈 | 全自研 | **80% 复用成熟框架** |

## 11.2 收益对比

| 维度 | 当前 | 4 阶段后 |
|---|---|---|
| 88-case 通过率 | ~85% | **> 95%** |
| LLM 幻觉率 | ~30% | **< 5%** |
| 单 case 成本 | $0.05-0.20 | **$0.02-0.08** |
| 失败 case 定位 | 30 分钟 | **< 1 分钟** |
| 危险操作拦截 | 无 | **OPA 强制** |
| 复杂分析能力 | 单查询 | **同比 / 下钻 / 归因** |
| HITL SLA | 无 | **< 5 分钟** |

## 11.3 团队能力建设

主流化路径同时带来：

- LangGraph 1.0 实战能力（业界主流）
- dbt Semantic Layer / Cube.js 经验
- SQLGlot / Apache Calcite 实战
- OPA / Cerbos Policy 引擎
- OpenTelemetry + LangFuse 观测栈
- Multi-Agent / Tool Calling 实战

**这些能力都是业界抢手技能**，不像自研 Runtime 是封闭生态。

---

# 十二、最终结论

原方案（[Talk_to_Data_Agent_Harness_升级架构方案说明书.md](./Talk_to_Data_Agent_Harness_升级架构方案说明书.md)）**核心思想是对的**，但**实现路径与业界主流方向相反**。

主流化升级路径的 3 个关键决策：

1. **保留 LangGraph 1.0**，让 subgraph 充当 Harness
2. **嵌入成熟框架**（dbt MetricFlow / SQLGlot / LangFuse / OPA），不自研
3. **Tool 粒度粗化**，LLM 决策负担不爆炸

**预期收益**：

- 投入：从 30-50 FTE × 12 月降到 **5-8 FTE × 12 月**
- 风险：从 7 阶段断崖式降到 4 阶段渐进
- 可行性：从"愿景蓝图"升级为"季度可交付"

---

## 附录 A：参考资源

### 业界主流工具

| 工具 | 用途 | 链接 |
|---|---|---|
| LangGraph 1.0 | 编排 / subgraph / HITL / Checkpointing | https://langchain-ai.github.io/langgraph/ |
| LangSmith | Trace / Eval / Production Monitoring | https://docs.smith.langchain.com/ |
| LangFuse | 开源 LLM Observability | https://langfuse.com/ |
| dbt Semantic Layer | Metric / Dimension / Entity 建模 | https://docs.getdbt.com/docs/build/about-metricflow |
| Cube.js | Semantic Layer + Federation + REST/GraphQL API | https://cube.dev/ |
| SQLGlot | SQL Parser / Generator / Transpiler | https://github.com/tobymao/sqlglot |
| Apache Calcite | SQL Optimizer / Federation | https://calcite.apache.org/ |
| OPA (Open Policy Agent) | Policy Engine | https://www.openpolicyagent.org/ |
| Instructor | LLM Structured Output | https://github.com/jxnl/instructor |
| OpenLLMetry | OpenTelemetry for LLM | https://github.com/traceloop/openllmetry |

### 相关文档

- [原方案文档](./Talk_to_Data_Agent_Harness_升级架构方案说明书.md)
- [回归测试用例](../regression_test_cases.csv)
- [全量测试用例](../test_cases.csv)

---

> **作者备注**：本方案不是要否定原方案，而是把原方案的**愿景**翻译成**可执行的工程路径**。原方案的核心思想（职责分离 + DSL + Security Kernel + HITL + Observability）已全部继承并落地；实施路径上的差异（保留 LangGraph vs 替换 LangGraph、自研 vs 嵌入成熟框架）才是真正决定成败的关键。