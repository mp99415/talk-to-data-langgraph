# Talk-to-Data 升级方案（修订版）

> 版本：V2.0（修订版）  
> 日期：2026-09-27  
> 配套文档：  
> - [Talk_to_Data_Agent_Harness_升级架构方案说明书.md](./Talk_to_Data_Agent_Harness_升级架构方案说明书.md)（原始 Agent Harness 方案）  
> - [Talk_to_Data_Mainstream_Upgrade_Plan.md](./Talk_to_Data_Mainstream_Upgrade_Plan.md)（主流化方案 V1）  
> 目标：基于前两版方案与项目反馈，输出**真正可落地的修订版方案**。

---

## 一、修订版相对前两版的变化

### 与"原始 Agent Harness 方案"对比

| 维度 | 原始方案 | 修订版 |
|---|---|---|
| Agent Runtime | 自研 | **保留 LangGraph，用 subgraph** |
| State Manager | 自研 | **LangGraph Checkpointer + Thread** |
| Memory | 自研三层 | **LangGraph Store + Postgres** |
| HITL Manager | 自研 | **LangGraph `interrupt`** |
| Trace | 自研 | **LangFuse + OpenTelemetry** |
| SQL 引擎 | 自研 Query Compiler | **SQLGlot（AST-first）** |

### 与"主流化方案 V1"对比

| 维度 | V1 | 修订版 |
|---|---|---|
| Semantic Layer | 交给 dbt/Cube | **保留 Enterprise Ontology 内核，dbt/Cube 仅作 BI 补充** |
| Permission Engine | 全部交给 OPA | **业务内核（Permission Compiler）+ OPA（PDP）分层** |
| Query Compiler | 字符串模板 | **AST-first（Logical AST → SQLGlot Expression → Dialect SQL）** |
| Tool 粒度 | 粗粒度 | **对外粗对内细（Agent API 粗，企业内核细）** |
| Phase 4 Federation | 6-12 月 | **12-18 月+ 后置** |
| FTE 估算 | 5-8 FTE × 12 月 | **按团队规模 3 档估算** |
| 收益数字 | 当成既成事实 | **明确标注为"目标值，待 88 case 实测"** |

---

## 二、核心原则（修订版最重要的 3 条）

### 原则 1：保留内核，替换基础设施

> **保留企业数据查询内核（Semantic / Permission / Validator），包装成 LangGraph 可调用的业务能力；用成熟组件替换基础设施层（Trace / Policy / SQL 解析）。**

```
不要: 现有系统 → 全部重写
而是: 现有内核 → 包装为业务能力 → 渐进替换基础设施层
```

### 原则 2：对外粗对内细

> **Agent Tool API 粗粒度（一类业务一个 Tool）；企业内部模块（Semantic / Permission / Compiler / Validator / Executor）保持细粒度清晰分层。**

### 原则 3：DSL 是节点内的中间表示，不是跨服务协议

> **DSL 是 LangGraph state 的一部分，在 sql_generator 节点内生成，在 permission_engine 节点内消费，不暴露成跨服务 API（避免 RPC 复杂度）。**

---

## 三、最终架构（修订版）

```
                        ┌──────────────────┐
                        │      User        │
                        └────────┬─────────┘
                                 ↓
                   ┌──────────────────────────┐
                   │   Agent Layer             │
                   │   LangGraph Subgraph      │
                   │                           │
                   │ Plan → Tool → Reflect     │
                   │ interrupt (HITL)         │
                   └────────────┬──────────────┘
                                ↓
                   ┌──────────────────────────┐
                   │  Enterprise Semantic      │
                   │  Kernel / Ontology        │  ← 保留为业务内核
                   │                           │
                   │ Entity / Metric           │
                   │ Dimension / Event         │
                   │ Relationship              │
                   │ Business Value            │
                   │ Physical Mapping          │
                   └────────────┬──────────────┘
                                ↓
                         Query DSL / Plan
                                ↓
                   ┌──────────────────────────┐
                   │ Permission Compiler       │  ← 保留为业务内核
                   │                           │
                   │ RBAC                      │
                   │ Table ACL                 │
                   │ Field ACL                 │
                   │ Row Policy Injector       │
                   │ User Reference Corrector  │
                   └────────────┬──────────────┘
                                ↓
                  ┌─────────────────────────────┐
                  │ Policy Decision Point       │  ← OPA / Cerbos
                  │ (OPA / Cerbos)              │
                  └────────────┬────────────────┘
                               ↓
                    Authorized Logical Plan
                               ↓
                   ┌──────────────────────────┐
                   │ Query Compiler            │  ← AST-first
                   │                           │
                   │ DSL → Logical AST         │
                   │ SQLGlot Expression        │
                   │ Optimizer                 │
                   │ Dialect Generator         │
                   └────────────┬──────────────┘
                                ↓
                          SQL / AST
                                ↓
                   ┌──────────────────────────┐
                   │ Security Validator        │  ← 保留为业务内核
                   │                           │
                   │ AST Validator             │
                   │ Cost / Risk Validator     │
                   │ DLP-like 字段脱敏          │
                   └────────────┬──────────────┘
                                ↓
                       SQL Execute
                                ↓
                          Result
                                ↓
                   ┌──────────────────────────┐
                   │ Result Kernel             │  ← 保留为业务内核
                   │ Normalize / Validate      │
                   │ Analyze / Insight         │
                   └────────────┬──────────────┘
                                ↓
                       Final Answer

横切关注点:
  OpenTelemetry + LangFuse + Grafana + OPA + Eval + Audit + HITL
```

---

## 四、4 阶段路线图（修订版）

| Phase | 时长 | 核心目标 | 主要风险 |
|---|---|---|---|
| **Phase 1** | 1-2 月 | 观测 + 节点 Instrument | 低 |
| **Phase 2** | 3-4 月 | DSL AST-first + Query Compiler | 中 |
| **Phase 3** | 4-6 月 | Agent Harness Subgraph + Tool 封装 | 中高 |
| **Phase 4+** | 12-18 月+ | Federation / Multi-source | 后置 |

---

# 五、Phase 1：观测 + 节点 Instrument（1-2 月）

## 5.1 目标

零业务逻辑改动，加 trace + eval + 节点级安全 policy。

## 5.2 主流工具栈（采纳）

| 能力 | 选型 |
|---|---|
| Trace | LangSmith / LangFuse / Arize Phoenix |
| Eval | LangSmith Evaluations / DeepEval / Ragas |
| LLM Token 监控 | OpenLLMetry (OTel) / LangSmith |
| 节点 Policy | OPA (Open Policy Agent) / Cerbos |
| Metrics Dashboard | Grafana + Prometheus |

## 5.3 落地步骤

### Step 1 (Week 1-2)：接 LangFuse

```python
from langfuse.decorators import observe, langfuse_context

@observe(name="sql_generator")
def sql_generator_node(state: dict) -> dict:
    # 业务逻辑保持不变
    llm = get_llm()
    sql = llm.invoke(...)
    # trace 自动记录 input/output/latency/token
    return {"sql": sql}
```

### Step 2 (Week 3-4)：regression_test_cases.csv 自动评估

```python
import sqlglot

def evaluate_sql_match(actual: str, expected: str) -> float:
    """基于 AST 的 SQL 相似度评分（不是字符串对比）"""
    try:
        ast_actual = sqlglot.parse_one(actual)
        ast_expected = sqlglot.parse_one(expected)
        return 1.0 if ast_actual.sql() == ast_expected.sql() else 0.0
    except Exception:
        return 0.0
```

### Step 3 (Week 5-6)：节点 Policy Guard（OPA）

```rego
package node_policy

default allow = false

allow {
    # sql_executor 必须有 permission_result.authorized=true
    input.permission_result.authorized == true
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
看板:
- 88 case P50/P95 延迟
- LLM token 消耗 / 单 case 成本
- 权限拦截率 / 失败率
- 节点级错误率 Top 5
```

## 5.4 收益（目标值，待 88 case 实测验证）

| 指标 | 当前 | Phase 1 后（目标） |
|---|---|---|
| 失败 case 定位时间 | ~30 分钟（人工翻 log） | **< 1 分钟**（LangFuse 一键定位） |
| 性能瓶颈识别 | 凭经验 | **Grafana 自动 Top 5** |
| 危险操作拦截 | 无 | **OPA 强制拦截** |
| Token 成本可见性 | 无 | **全链路统计** |

---

# 六、Phase 2：DSL AST-first + Query Compiler（3-4 月）

## 6.1 目标

让 LLM 输出强类型 DSL（不是 SQL 字符串），由 AST-first 编译器确定性渲染 SQL。

**关键修正（vs V1）**：字符串模板仅作 Demo，生产必须 AST-first。

## 6.2 主流工具栈（采纳）

| 能力 | 选型 |
|---|---|
| DSL Schema 校验 | Pydantic + JSON Schema |
| LLM 输出结构化 | OpenAI Structured Outputs / Instructor |
| SQL Parser/Generator | SQLGlot |
| SQL 优化 | SQLGlot Optimizer |

## 6.3 双轨并行策略（关键）

```
Track A: 简单查询（~60%）走 Query DSL + AST Compiler
Track B: 复杂查询（~40%）继续 LLM SQL Generator + 增强保护

双轨并行 3 个月：
- Track A 的 SQL 跟原 SQL 自动 diff（AST compare）
- Track A 通过率 > 90% 后逐步扩大比例
- Track B 保留 LLM fallback
```

## 6.4 DSL Schema（Pydantic 强类型）

```python
from pydantic import BaseModel, Field
from typing import List, Literal

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
    field: str
    start: str
    end: str

class Filter(BaseModel):
    table: str
    field: str
    operator: Literal["=", "!=", "<", ">", "IN"] = "="
    value: str

class QueryDSL(BaseModel):
    """业务查询 DSL：只描述做什么，不描述怎么做 SQL"""
    grain: Literal["SCALAR", "GROUPED", "DETAIL", "RANKING"] = "SCALAR"
    main_table: str = "orders"
    metrics: List[Metric] = []
    dimensions: List[Dimension] = []
    filters: List[Filter] = []
    time: TimeRange | None = None
    limit: int | None = None
```

## 6.5 Query Compiler（AST-first，**不是**字符串模板）

### ❌ V1 的危险做法（仅作 Demo）

```python
# V1 的字符串拼接 —— 生产环境禁止
sql = f"SELECT {', '.join(select_fields)} FROM `{dsl.main_table}`"
if where_parts:
    sql += f" WHERE {' AND '.join(where_parts)}"
```

### ✅ 修订版：AST-first（Logical AST → SQLGlot Expression）

```python
import sqlglot
from sqlglot import exp

class QueryCompiler:
    """DSL → AST → Optimized SQL（AST-first）"""

    def compile(self, dsl: QueryDSL, dialect: str = "mysql") -> str:
        # 1. DSL Validation（Pydantic 强类型）
        dsl.validate()

        # 2. DSL → Logical AST（SQLGlot Expression 树）
        select_exprs = []
        group_exprs = []

        for m in dsl.metrics:
            col = exp.column(m.field, table=m.table)
            agg = getattr(exp, m.aggregation.lower())(this=col)
            select_exprs.append(exp.alias_(agg, alias=m.name))

        for d in dsl.dimensions:
            col = exp.column(d.field, table=d.table)
            select_exprs.append(exp.alias_(col, alias=d.name))
            group_exprs.append(col)

        # 3. WHERE 条件
        where_exprs = []
        for f in dsl.filters:
            col = exp.column(f.field, table=f.table)
            value = exp.Literal.string(f.value)
            op = {
                "=": exp.EQ,
                "!=": exp.NEQ,
                "<": exp.LT,
                ">": exp.GT,
                "IN": exp.In,
            }[f.operator]
            where_exprs.append(op(this=col, expression=value))

        if dsl.time:
            time_col = exp.column(dsl.time.field)
            where_exprs.append(exp.GTE(this=time_col, expression=exp.Literal.string(dsl.time.start)))
            where_exprs.append(exp.LT(this=time_col, expression=exp.Literal.string(dsl.time.end)))

        # 4. 构建 Logical Plan
        ast = exp.Select(
            expressions=select_exprs,
            **{"from": exp.from_(exp.table(dsl.main_table))}
        )
        if where_exprs:
            ast = ast.where(exp.and_(*where_exprs))
        if group_exprs:
            ast = ast.group_by(*group_exprs)
        if dsl.limit:
            ast = ast.limit(exp.Literal.number(dsl.limit))

        # 5. SQLGlot Optimizer（CBO / 谓词下推 / 投影裁剪）
        from sqlglot.optimizer import optimize
        optimized = optimize(
            ast,
            schema=dialect,  # 从 schema_builder 加载真实 schema
        )

        # 6. Dialect Generator
        return optimized.sql(dialect=dialect)
```

**核心优势**：

- ✅ SQL 注入天然防御（无字符串拼接）
- ✅ 方言适配（MySQL / PG / Doris 一行切换）
- ✅ 优化器可介入（谓词下推、投影裁剪）
- ✅ 测试可靠（AST 对比而非字符串对比）

## 6.6 LLM 输出 DSL（Instructor + Pydantic）

```python
import instructor
from openai import OpenAI

client = instructor.from_openai(OpenAI())

def parse_query_to_dsl(user_query: str, semantic_layer: dict) -> QueryDSL:
    """LLM 输出强类型 DSL，不是 SQL"""
    response = client.chat.completions.create(
        model="gpt-4",
        response_model=QueryDSL,
        messages=[
            {"role": "system", "content": f"输出 JSON DSL。语义层：{semantic_layer}"},
            {"role": "user", "content": user_query},
        ],
        max_retries=2,  # 校验失败自动 retry
    )
    return response
```

## 6.7 切换比例渐进

```
Track A 切换策略:
- Week 1-2: 10% case 走 Track A（监控延迟 / 成功率）
- Week 3-4: 50% case 走 Track A
- Week 5-6: 80% case 走 Track A
- Week 7-8: 95% case 走 Track A（5% 失败自动回退到 Track B）

监控指标:
- Track A 通过率 > 90%（不达标则暂停切换）
- Track A 延迟 < 原方案
- regression_test_cases.csv 不退化
```

## 6.8 收益（目标值）

| 指标 | 当前 | Phase 2 后（目标） |
|---|---|---|
| LLM 幻觉率 | ~30% | **< 10%**（保守目标，需 88 case 实测） |
| SQL 执行错误率 | ~15% | **< 5%** |
| 单 case 成本 | $0.05-0.20 | **$0.03-0.10**（保守目标） |
| 88-case 通过率 | ~85% | **> 92%** |

---

# 七、Phase 3：Agent Harness Subgraph + Tool 封装（4-6 月）

## 7.1 目标

复杂分析能力（同比 / 下钻 / 异常归因）通过 Agent 动态编排，HITL 无缝集成。

## 7.2 主流工具栈（采纳）

| 能力 | 选型 |
|---|---|
| 动态编排 | LangGraph 1.0 subgraph + interrupt |
| Multi-Agent | LangGraph Multi-Agent Supervisor |
| Tool Registry | LangGraph ToolNode + Function Calling |
| HITL | LangGraph `interrupt_before` / `interrupt_after` |
| State 管理 | LangGraph Checkpointer + Thread |
| Memory | LangGraph Store + Postgres Backend |

## 7.3 关键决策：保留 LangGraph，让 subgraph 当 Harness

```python
from langgraph.graph import StateGraph, START, END

# Agent Subgraph（动态决策层）
class AgentState(TypedDict):
    user_query: str
    plan: List[str]
    step: int
    max_steps: int
    tool_results: List[dict]

agent_subgraph = StateGraph(AgentState)
agent_subgraph.add_node("understand", understand_node)
agent_subgraph.add_node("plan", plan_node)
agent_subgraph.add_node("tool_executor", tool_executor_node)
agent_subgraph.add_node("reflect", reflect_node)

agent_subgraph.add_edge(START, "understand")
agent_subgraph.add_edge("understand", "plan")
agent_subgraph.add_edge("plan", "tool_executor")
agent_subgraph.add_edge("tool_executor", "reflect")
agent_subgraph.add_conditional_edges(
    "reflect",
    lambda s: "continue" if s["step"] < s["max_steps"] else "end",
    {"continue": "plan", "end": END}
)

# 主图：把 Agent Subgraph 当一个节点
main_graph = StateGraph(GraphState)
main_graph.add_node("agent_harness", agent_subgraph.compile())
main_graph.add_edge("query_validator", "agent_harness")
main_graph.add_edge("agent_harness", "security_kernel")
```

## 7.4 Tool 设计：对外粗对内细

### Agent Tool API（粗粒度）

```python
from langchain_core.tools import tool

@tool
def execute_business_query(user_id: str, query_dsl: QueryDSL) -> QueryResult:
    """业务查询工具（粗粒度，一类业务一个 Tool）"""
    pass

@tool
def compare_periods(
    user_id: str,
    current_dsl: QueryDSL,
    previous_dsl: QueryDSL
) -> ComparisonResult:
    """对比两个时间段的指标（同比、环比）"""
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
    """异常归因"""
    pass
```

### Tool 内部模块（细粒度保留）

```
execute_business_query(user_id, query_dsl)
   ↓
1. Semantic Resolver (业务语义 → 物理映射)
2. Query Planner (DSL → Logical Plan)
3. Permission Compiler (注入 Row Policy / Field ACL / User Reference)
4. OPA PDP (RBAC 决策)
5. SQL Compiler (AST-first)
6. Security Validator (AST 校验 + Cost / Risk)
7. Executor (执行 SQL)
```

**对外一个 Tool，对内七个模块**——这是关键原则。

## 7.5 HITL 用 LangGraph interrupt

```python
from langgraph.graph import interrupt

def sensitive_query_node(state):
    """敏感查询节点：大规模导出需要 HITL"""
    if state["query_dsl"].estimated_rows > 100000:
        decision = interrupt({
            "type": "approval_required",
            "reason": "large_data_export",
            "estimated_rows": 100000,
            "preview": state["query_dsl"].preview()
        })
        if decision != "approved":
            return {"status": "DENIED", "reason": "human_rejected"}
    return execute_query(state)
```

## 7.6 Memory 用 LangGraph Store

```python
from langgraph.store.postgres import PostgresStore

# 主流模式：LangGraph Store + Postgres 后端
store = PostgresStore(conn_string="postgresql://...")

# 三层 Memory：
# - Conversation Memory: namespace=("conversation", user_id)
# - Query State Memory: namespace=("query_state", user_id, thread_id)
# - Task Memory: state["task_id"] 自动管理
```

## 7.7 收益（目标值）

| 能力 | Phase 2 后 | Phase 3 后 |
|---|---|---|
| 同比 / 环比 | ❌ 手工拆解 | ✅ 自动 Tool |
| 下钻分析 | ❌ 手工拆解 | ✅ 自动 Tool |
| 异常归因 | ❌ 手工拆解 | ✅ 自动 Tool |
| 大规模导出 HITL | ❌ 无拦截 | ✅ 强制审批 |
| 多轮对话恢复 | ❌ 部分支持 | ✅ Checkpointer 原生 |

---

# 八、Phase 4+：Federation / Multi-source（12-18 月+，后置）

**重要**：本阶段**不进 12 月内 roadmap**，仅作长期愿景。

## 8.1 主流工具栈

| 能力 | 选型 |
|---|---|
| 多方言 SQL | SQLGlot transpiler |
| OLAP / Vector | Cube.js Federation / StarRocks / Doris |
| GraphQL 联邦 | Apollo Federation / Hasura |
| Document DB | MongoDB Atlas SQL Interface |

## 8.2 不自研 DAX / KQL 引擎

- DAX：用 Analysis Services TOM/XMLA 协议
- KQL：用 Azure Data Explorer SDK
- 自研 50+ FTE 项目，**不值得**

---

# 九、新增章节（V1 缺失，本版补全）

## 9.1 Eval / 评测体系

```
Eval 层次:
├── 单元测试
│   └── Query Compiler / Permission Compiler
├── 集成测试
│   └── Semantic Resolver / Security Validator
├── E2E 测试
│   └── regression_test_cases.csv (20 case Golden)
│   └── test_cases.csv (88 case 全量回归)
├── LLM 输出评估
│   ├── 幻觉率（Instructor + Pydantic 校验失败率）
│   ├── Schema 一致性（输出字段是否在 schema 内）
│   └── 业务准确性（人工 spot-check 20%）
├── 业务指标
│   ├── 查询成功率 / 平均延迟
│   ├── 用户满意度（👍/👎）
│   └── 重复查询率
└── A/B 测试
    └── Track A vs Track B 用户体验 diff
```

## 9.2 Schema 检索策略（RAG）

```
V1 完全缺失
schema > 50 表时，全量装入 prompt 不可行

主流做法:
1. Schema 索引（Embedding 模型）
2. User Query → Top-K 相关表/列
3. 仅把 Top-K 表 schema + LLM 生成 DSL

工具栈:
- Embedding: OpenAI text-embedding-3 / bge-large-zh
- 向量库: pgvector / Qdrant / Milvus
- 检索: Vanna.ai 风格的 RAG
```

## 9.3 DSL 版本演进策略

```
DSL 会演进:
v1: SCALAR / GROUPED / DETAIL
v2: + RANKING
v3: + COMPARISON / TREND

历史 case 的 DSL 输出是 v1,新代码是 v3
怎么处理:
- DSL schema 用 Pydantic version 字段
- Migration 脚本（v1 → v3 自动转换）
- 强制重跑历史 case（E2E test）
- 版本路由（v1 DSL 走 v1 Compiler）
```

## 9.4 Trace 数据治理

```
Trace 数据量会爆炸:
- 88 case × 40节点 × 5 trace 字段 = 17,600 条/天（开发）
- 生产 1000 用户 × 50 查询/天 × 40 节点 = 2M trace/天

策略:
- 采样: P0 100%, P1 10%, P2 1%
- 保留周期: 热数据 7 天，冷数据 30 天后归档
- 隐私: PII 字段 trace 时脱敏
- 合规: 跨租户 trace 严格隔离
```

## 9.5 跨团队协调成本

```
企业项目不只技术:
- DBA 团队: 语义建模 review
- 安全团队: 权限方案 review  
- 业务方: Business Owner sign-off
- 法务: 数据合规 audit
- SRE: 部署 / 监控 / SLA

FTE 估算应包含:
- 技术 5 FTE
- 跨团队协调 2-3 FTE
- 总 7-8 FTE（中型团队）
```

---

# 十、FTE 重新估算（按团队规模 3 档）

## 10.1 小团队（3-5 人）

**目标**：完成 Phase 1 + 部分 Phase 2  
**周期**：6-9 月  
**FTE·月**：20-30

```
角色:
- 后端 Lead (1 人，全程)
- 全栈工程师 (2 人，全程)
- DevOps 兼职 (0.5 人 × 3 月)

不做的:
- Phase 3 (Agent Subgraph) - 推迟到下一阶段
- Phase 4 (Federation) - 不进 roadmap
- 复杂 Permission Compiler 改造 - 仅 Policy Guard
```

## 10.2 中型团队（8-12 人）

**目标**：完成 Phase 1-3  
**周期**：12 月  
**FTE·月**：50-70

```
角色:
- 后端 Lead (1 人，全程)
- 后端工程师 (3 人，全程)
- LLM/Agent Engineer (1 人，全程)
- DBA / Semantic Lead (1 人，全程)
- 权限专家 (1 人，全程)
- QA / Eval (1 人，全程)
- DevOps (1 人，全程)
- 跨团队协调 (0.5-1 人，全程)
```

## 10.3 大型团队（>20 人）

**目标**：含 Phase 4 Federation  
**周期**：18 月+  
**FTE·月**：100-150

```
新增角色（vs 中型团队）:
- 多数据源 DBA (1-2 人)
- 多方言 SQL 专家 (1-2 人)
- Cube.js / Federation 专家 (1 人)
- 安全 / 合规 (1-2 人)
- SRE (1-2 人)
```

---

# 十一、与原 Agent Harness 方案的逐章节对照

| 章节 | 原方案 | 修订版 |
|---|---|---|
| 第二章 总体架构 7 层 | 自研 Runtime 7 层 | **保留 7 层思想，但每层用成熟组件替代** |
| 第三章 职责边界 | ✅ 保留 | ✅ 完全保留 |
| 第四章 Agent Harness | 自研 10 子模块 | **LangGraph 1.0 subgraph + interrupt + Store + ToolNode** |
| 第六章 Tool Registry | 抽象 JSON schema | **LangChain Function Calling + ToolNode** |
| 第七章 Tool 分层 | 细粒度 5 层 | **对外粗对内细** |
| 第八章 Query State | 保留业务语义 | ✅ 保留（DSL = Query State 增强） |
| 第十章 Semantic Layer | 自研 Entity/Metric/Dimension | **保留 Ontology 内核，dbt 仅 BI 补充** |
| 第十五章 Query DSL | 描述性 JSON | ✅ 保留 + Pydantic 校验 + Instructor |
| 第十七章 Query Compiler | 8 子模块字符串拼接 | **AST-first + SQLGlot** |
| 第十八章 SQL Generator | LLM 输出 DSL 后渲染 | ✅ 完全保留 |
| 第十九章 Security Kernel | 9 子模块 | **业务内核 + OPA 分层** |
| 第二十八章 HITL | 自研 HITL Manager | **LangGraph interrupt** |
| 第二十九章 Observability | 自研 Trace | **LangFuse + OpenTelemetry + Grafana** |
| 第三十一章 Dify 迁移 | 4 Phase | **渐进式 4 Phase + 双轨** |
| 第三十四章 实施路线 | 7 Phase 无时间 | **4 Phase + 时间表 + 风险** |
| 第三十七章 核心结论 | ✅ 保留思想 | ✅ 完全保留 |

---

# 十二、最终决策表

## 12.1 应该保留的（✅ 主流方向正确）

| 决策 | 理由 |
|---|---|
| ✅ LangGraph 编排 | 已原生支持 subgraph/interrupt/Checkpoint/Store |
| ✅ Subgraph 动态决策 | LangGraph 自带，不需自研 |
| ✅ SQLGlot | AST-first 必经之路 |
| ✅ OpenTelemetry + LangFuse | 业界标准 Trace |
| ✅ OPA / Cerbos | 业界标准 PDP |
| ✅ 双轨迁移 | 工程最务实 |
| ✅ DSL 概念 | 降 LLM 幻觉核心 |
| ✅ AST Validation | 安全必备 |
| ✅ 粗粒度 Agent Tool API | LLM 决策负担可控 |

## 12.2 应该回退的（⚠️ 主流化过头）

| 决策 | 回退原因 |
|---|---|
| ⚠️ dbt/Cube 替代 Semantic Layer | 企业 Ontology 远超 Metric Layer 范围 |
| ⚠️ OPA 替代 Permission Engine | OPA 仅作 PDP，业务权限要自研内核 |
| ⚠️ String-first Query Compiler | 生产严禁字符串拼接，必须 AST-first |
| ⚠️ Tool 内部模块粗粒度化 | 对外粗对内细，不要混淆 |
| ⚠️ Phase 4 Federation 6-12 月 | 应后置到 12-18 月+ |
| ⚠️ 5-8 FTE 当成既成事实 | 应按团队规模 3 档估算 |

## 12.3 新增章节（V1 缺失）

- Eval / 评测体系
- Schema 检索策略（RAG）
- DSL 版本演进
- Trace 数据治理
- 跨团队协调成本

---

# 十三、最终结论

## 13.1 修订版的定位

> **这是一份"思想正确、路径主流、落地务实"的升级方案。**  
>   
> 保留：LangGraph + SQLGlot + LangFuse + OPA + 双轨迁移 + DSL  
> 回退：dbt/Cube 替代 Semantic、OPA 替代 Permission、String-first Compiler、Phase 4 提前  
> 新增：Eval 体系、Schema RAG、DSL 版本治理、Trace 数据治理、跨团队协调

## 13.2 实施节奏

```
Month 0-1:   Phase 1 启动（LangFuse + Trace）
Month 2:     Phase 1 完成（Eval 自动化）
Month 3-4:   Phase 2 启动（DSL schema + AST Compiler）
Month 5-6:   Phase 2 完成（Track A 95%）
Month 7-9:   Phase 3 启动（LangGraph subgraph + Tool）
Month 10-12: Phase 3 完成（Agent 复杂分析）
Month 13+:   Phase 4+ 评估（Federation 立项）
```

## 13.3 给团队的核心建议

1. **不要推翻现有 Query Plan / Semantic / Permission / Validator**——它们是企业内核
2. **包装现有能力为 LangGraph 可调用的业务 Tool**——这是 Phase 3 的核心
3. **基础设施层用成熟组件替换**（Trace / Policy / SQL Parser）——这是 ROI 最高的
4. **DSL 是节点内的中间表示，不是跨服务协议**——避免 RPC 复杂度
5. **保持 88 case 通过率不下降**——双轨迁移是关键保险

---

## 附录 A：参考资源

### 主流工具

| 工具 | 用途 | 链接 |
|---|---|---|
| LangGraph 1.0 | 编排 / subgraph / HITL / Checkpointing | https://langchain-ai.github.io/langgraph/ |
| LangSmith | Trace / Eval / Production Monitoring | https://docs.smith.langchain.com/ |
| LangFuse | 开源 LLM Observability | https://langfuse.com/ |
| OpenLLMetry | OpenTelemetry for LLM | https://github.com/traceloop/openllmetry |
| SQLGlot | SQL Parser / Generator / Transpiler | https://github.com/tobymao/sqlglot |
| Apache Calcite | SQL Optimizer / Federation | https://calcite.apache.org/ |
| OPA | Policy Engine | https://www.openpolicyagent.org/ |
| Cerbos | RBAC / ABAC | https://www.cerbos.dev/ |
| Instructor | LLM Structured Output | https://github.com/jxnl/instructor |
| dbt Semantic Layer | Metric / Dimension / Entity 建模 | https://docs.getdbt.com/docs/build/about-metricflow |
| Cube.js | Semantic Layer + Federation + API | https://cube.dev/ |
| pgvector | Postgres 向量检索 | https://github.com/pgvector/pgvector |

### 相关文档

- [原 Agent Harness 方案](./Talk_to_Data_Agent_Harness_升级架构方案说明书.md)
- [主流化方案 V1](./Talk_to_Data_Mainstream_Upgrade_Plan.md)
- [回归测试用例](../regression_test_cases.csv)
- [全量测试用例](../test_cases.csv)

---

> **作者备注**：本修订版**不是否定前两版方案**，而是把它们整合 + 修正 + 补全。前两版的**核心思想（职责分离 + DSL + Security Kernel + HITL + Observability）已全部继承并落地**；前两版**主流化过头的地方（dbt/Cube 替代 Semantic、OPA 替代 Permission、String-first Compiler、Phase 4 提前）已明确回退**；前两版**缺失的章节（Eval / RAG / DSL 版本治理 / Trace 数据治理 / 跨团队协调）已补全**。最终交付：**一份可在 12-18 月内由中型团队（8-12 人）落地的修订版方案**。