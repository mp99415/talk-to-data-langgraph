# 企业级 Talk-to-Data Agent Harness 升级架构方案说明书

> 版本：V1.0  
> 目标：在保留现有 Semantic Layer、Query State、Permission Engine、AST Security、Query Plan 等核心能力的基础上，将当前固定 Workflow 升级为 **Agent Harness + Deterministic Analytics Kernel**。
>
> 核心原则：**Agent 负责“决定下一步做什么”，确定性内核负责“决定什么可以做、怎么执行、执行结果是否可信”。**

---

## 一、升级目标

当前 Talk-to-Data 已经不是简单的 Text-to-SQL，而是具备：

```text
自然语言理解
    ↓
Query State
    ↓
业务语义解析
    ↓
Schema Binding
    ↓
Value Resolution
    ↓
Query Plan
    ↓
SQL
    ↓
AST
    ↓
RBAC
    ↓
Row Permission
    ↓
Field Permission
    ↓
SQL Execution
    ↓
Result Validation
```

下一阶段重点不是继续增加 Dify 节点，而是解决：

1. 流程过于固定
2. 所有问题都走同一条 Pipeline
3. 复杂分析难以动态拆解
4. 一个问题需要多次查询时扩展困难
5. SQL Generator 自由度仍然偏高
6. Semantic / Query Plan / SQL 的职责边界越来越复杂
7. 未来接入 DAX / KQL / API / Ontology 不够自然
8. Workflow 越来越像一个巨型状态机

升级目标：

```text
                 Enterprise Analytics Agent
                           │
                           ↓
                    Agent Harness
                           │
              ┌────────────┼────────────┐
              ↓            ↓            ↓
         Semantic       Query        Analysis
           Tools         Tools         Tools
              │            │            │
              └────────────┼────────────┘
                           ↓
                     Query DSL
                           ↓
                   Query Compiler
                           ↓
                SQL / DAX / KQL / API
                           ↓
                    Security Kernel
                           ↓
                       Executor
                           ↓
                  Result / Insight
```

---

# 二、总体架构

升级后的整体架构分为 7 层：

```text
┌───────────────────────────────────────────────────────────┐
│                    Layer 7 Experience                     │
│ Chat / API / BI / Dashboard / Copilot / Voice            │
└──────────────────────────┬────────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────────┐
│                    Layer 6 Agent                          │
│ Enterprise Analytics Agent                               │
│ Intent / Planning / Reasoning / Tool Selection            │
└──────────────────────────┬────────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────────┐
│                    Layer 5 Agent Harness                   │
│ State / Memory / Tool Registry / Policy / Loop / HITL     │
└──────────────────────────┬────────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────────┐
│                    Layer 4 Semantic Layer                  │
│ Entity / Metric / Dimension / Value / Event / Ontology    │
│ Schema Builder / Semantic Resolver / Value Resolver       │
└──────────────────────────┬────────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────────┐
│                    Layer 3 Query Engine                    │
│ Query State / Query DSL / Query Plan / Query Compiler     │
└──────────────────────────┬────────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────────┐
│                    Layer 2 Security Kernel                 │
│ AST / RBAC / Row Permission / Field Permission / Policy  │
└──────────────────────────┬────────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────────┐
│                    Layer 1 Data Runtime                    │
│ SQL / DAX / KQL / DB / API / Vector / OLAP               │
└───────────────────────────────────────────────────────────┘
```

最核心的变化：

> **Agent 不再等于整个 Talk-to-Data。Agent 只是上层的动态决策器。**

---

# 三、核心设计原则

## 3.1 Agent ≠ Security

绝对不能：

```text
Agent
 ↓
SQL
 ↓
Database
```

必须：

```text
Agent
 ↓
Query DSL
 ↓
Query Compiler
 ↓
AST
 ↓
Permission Engine
 ↓
Authorized SQL
 ↓
Database
```

## 3.2 Agent ≠ Query Compiler

Agent 决定：

> 我要完成什么分析任务？

Compiler 决定：

> 这个业务查询如何确定性地编译成 SQL / DAX / KQL？

## 3.3 Agent ≠ Permission Engine

Agent 可以提出：

> 我想查询这些数据。

Permission Engine 决定：

> 当前用户到底能不能查询这些数据。

---

# 四、Agent Harness 定位

Agent Harness 是整个升级的核心。

它不是 LLM，而是 Agent 的运行时控制层，负责：

```text
生命周期
状态
工具
权限
执行
循环
错误
重试
人工介入
日志
Trace
```

建议结构：

```text
Agent Harness
│
├── Agent Runtime
├── State Manager
├── Memory Manager
├── Tool Registry
├── Tool Executor
├── Policy Guard
├── Execution Loop
├── Error Recovery
├── HITL Manager
└── Observability
```

---

# 五、Agent Runtime

Agent Runtime 负责：

```text
User Question
      ↓
Agent
      ↓
Decision
      ↓
Tool Call
      ↓
Tool Result
      ↓
Agent
      ↓
Next Tool
      ↓
...
      ↓
Final Answer
```

设置硬性执行限制：

```json
{
  "max_steps": 10,
  "max_tool_calls": 5,
  "timeout_seconds": 60
}
```

---

# 六、Tool Registry

统一 Tool Contract：

```json
{
  "name": "resolve_business_semantic",
  "description": "将用户业务问题解析为企业业务语义",
  "input_schema": {},
  "output_schema": {},
  "security_level": "READ",
  "requires_permission": true,
  "side_effect": false
}
```

每个 Tool 至少定义：

```text
name
description
input_schema
output_schema
security_level
requires_permission
side_effect
timeout
retry_policy
```

---

# 七、Tool 分层

## 7.1 Conversation Tools

```text
query_state.read
query_state.update
query_state.reset
clarification.create
clarification.resolve
```

## 7.2 Semantic Tools

```text
semantic.resolve
metric.resolve
entity.resolve
dimension.resolve
value.resolve
schema.get
```

## 7.3 Query Tools

```text
query_plan.build
query_dsl.build
query.compile
query.validate
```

## 7.4 Execution Tools

```text
query.authorize
query.execute
query.result
```

## 7.5 Analysis Tools

```text
result.summarize
result.compare
result.rank
result.trend
result.drilldown
result.explain
```

---

# 八、Query State 设计

现有 Query State 应继续保留：

```json
{
  "version": 3,
  "entity": null,
  "metrics": [],
  "dimensions": [],
  "filters": [],
  "time": null,
  "ranking": null,
  "comparison": null,
  "extensions": {}
}
```

核心原则：

> **Query State 只保存业务语义，不保存物理数据库字段。**

正确：

```json
{
  "metrics": [
    {
      "name": "销售额"
    }
  ]
}
```

不要：

```json
{
  "metrics": [
    {
      "table": "orders",
      "field": "amount"
    }
  ]
}
```

物理字段绑定属于 Semantic Resolution / Query Plan 阶段。

---

# 九、Clarification State

Clarification 应成为 Harness Task State，而不是依赖固定 Workflow 跳转。

```text
Agent
 ↓
发现 ambiguity
 ↓
Harness
 ↓
创建 pending_clarification
 ↓
暂停 Task
 ↓
用户回答
 ↓
Clarification Resolver
 ↓
Query State Merger
 ↓
继续执行
```

示例：

```json
{
  "status": "PENDING",
  "source": "SEMANTIC",
  "type": "FIELD",
  "reason": "FIELD_AMBIGUOUS",
  "target": {
    "type": "FIELD",
    "concept": "地区"
  },
  "question": {
    "text": "你指的是客户所在地区，还是销售区域？"
  },
  "candidates": [],
  "context": {
    "query_state": {},
    "rewritten_question": ""
  }
}
```

> Clarification Flow 不经过 Context Question Rewriter。

---

# 十、Semantic Layer

建议正式定义：

```text
Business Semantic Layer
│
├── Entity
├── Metric
├── Dimension
├── Value
├── Event
├── Relationship
├── Rule
└── Physical Mapping
```

---

# 十一、Entity

示例：

```json
{
  "entity": "Company",
  "label": "公司",
  "physical_mapping": {
    "table": "customers",
    "key": "id",
    "name_field": "name"
  }
}
```

---

# 十二、Metric

示例：

```json
{
  "metric": "sales_amount",
  "label": "销售额",
  "expression": {
    "aggregation": "SUM",
    "table": "orders",
    "field": "amount"
  }
}
```

对于公司数量：

```json
{
  "metric": "company_count",
  "label": "公司数量",
  "expression": {
    "aggregation": "COUNT_DISTINCT",
    "table": "customers",
    "field": "id"
  }
}
```

这样：

> “今年有多少家公司产生订单？”

不会再让 SQL Generator 自己决定 COUNT 还是 COUNT DISTINCT。

---

# 十三、Relationship

正式加入业务关系：

```json
{
  "name": "customer_has_order",
  "source": {
    "entity": "Company",
    "field": "id"
  },
  "target": {
    "entity": "Order",
    "field": "customer_id"
  },
  "cardinality": "ONE_TO_MANY"
}
```

于是：

```text
有订单的公司
```

可以表达成：

```text
RELATION_EXISTS(customer_has_order)
```

而不是错误地：

```sql
orders.status = 'has_order'
```

---

# 十四、Value Semantic Layer

现有：

```text
semantic_dimensions
semantic_dimension_values
semantic_value_aliases
```

建议形成：

```text
User Value
    ↓
Alias
    ↓
Business Value
    ↓
Physical Value
```

例如：

```text
“已产生”
   ↓
Alias
   ↓
“已完成”
   ↓
COMPLETED
```

核心原则：

> LLM 不负责猜 Physical Value，由 Value Resolver 根据语义元数据和业务值映射确定。

---

# 十五、Query DSL

这是升级中最重要的新层之一。

不要：

```text
Semantic Resolver
 ↓
SQL Generator
```

改成：

```text
Semantic Resolver
 ↓
Query DSL
 ↓
Query Compiler
 ↓
SQL
```

Query DSL 描述业务查询，而不是描述 SQL。

例如：

> 今年有多少家公司产生了订单？

```json
{
  "version": 1,
  "query": {
    "grain": "SCALAR"
  },
  "metrics": [
    {
      "name": "company_count"
    }
  ],
  "filters": [
    {
      "type": "RELATION_EXISTS",
      "relation": "customer_has_order"
    }
  ],
  "time": {
    "dimension": "order_date",
    "range": "CURRENT_YEAR"
  }
}
```

---

# 十六、Query DSL Grain

必须定义：

```text
SCALAR
GROUPED
DETAIL
RANKING
TREND
COMPARISON
```

### SCALAR

```text
今年销售额是多少？
```

只输出聚合结果，不应该出现 GROUP BY / LIMIT。

### GROUPED

```text
每家公司今年销售额是多少？
```

允许：

```text
GROUP BY customers.name
```

### RANKING

```text
今年销售额最高的10家公司
```

允许：

```text
GROUP BY
ORDER BY
LIMIT 10
```

### DETAIL

```text
今年有哪些订单？
```

允许：

```text
LIMIT
```

---

# 十七、Query Compiler

Query Compiler：

```text
Query DSL
    ↓
DSL Validation
    ↓
Logical Plan
    ↓
Physical Plan
    ↓
SQL / DAX / KQL
```

内部建议：

```text
Query Compiler
│
├── DSL Validator
├── Semantic Compiler
├── Relation Compiler
├── Filter Compiler
├── Time Compiler
├── Metric Compiler
├── Grain Compiler
├── Ranking Compiler
└── SQL Renderer
```

---

# 十八、SQL Generator 的定位变化

当前：

```text
Query Plan
 ↓
SQL Generator
```

升级后：

```text
Query DSL
 ↓
Query Compiler
 ↓
SQL Renderer
```

LLM 可以参与：

```text
DSL → Logical Plan
```

但：

```text
Logical Plan → SQL
```

尽量确定性编译。

这样可以显著降低：

- COUNT / COUNT DISTINCT 错误
- GROUP BY 错误
- LIMIT 错误
- JOIN 错误
- 时间范围错误
- Relation Exists 错误

---

# 十九、Security Kernel

Security Kernel 是整个系统的安全边界：

```text
Security Kernel
│
├── Schema Guard
├── AST Parser
├── SQL Validator
├── RBAC
├── Table Permission
├── Field Permission
├── Row Permission
├── Join Permission
├── Policy Engine
└── Authorized SQL
```

执行链：

```text
Agent
 ↓
Query DSL
 ↓
Query Compiler
 ↓
SQL
 ↓
AST
 ↓
Permission Engine
 ↓
Authorized SQL
 ↓
Executor
```

Agent 永远不能直接访问数据库。

---

# 二十、Tool Policy

Harness 应对 Tool 设置 Policy：

```json
{
  "tool": "query.execute",
  "policy": {
    "requires_authorization": true,
    "requires_ast": true,
    "requires_permission_check": true
  }
}
```

即使 Agent 发起 `execute_query`，Harness 也必须先经过：

```text
AST
 ↓
Permission
 ↓
Security
```

---

# 二十一、Agent Execution Loop

标准循环：

```text
START
 ↓
UNDERSTANDING
 ↓
PLANNING
 ↓
TOOL CALL
 ↓
OBSERVE
 ↓
VALIDATE
 ↓
CONTINUE?
 ├── YES → TOOL CALL
 └── NO → FINAL ANSWER
```

必须有：

```text
max_steps
max_tool_calls
timeout
token_budget
query_budget
```

---

# 二十二、复杂分析能力

例如：

> 为什么今年华东销售额比去年下降？

动态执行：

```text
1. 查询今年华东销售额
2. 查询去年华东销售额
3. 计算同比
4. 按公司拆分
5. 找下降最大的公司
6. 继续钻取
7. 生成解释
```

对应：

```text
Agent
 │
 ├── Query Tool
 ├── Query Tool
 ├── Comparison Tool
 ├── Drilldown Tool
 ├── Query Tool
 └── Insight Tool
```

---

# 二十三、Result Layer

查询结果不要直接交给 LLM：

```text
SQL Result
 ↓
Result Normalizer
 ↓
Result Validator
 ↓
Result Analyzer
 ↓
Insight Generator
 ↓
Final Answer
```

Result Validator 检查：

```text
字段
数据类型
聚合结果
缺失字段
空结果
异常结果
```

---

# 二十四、Analysis Tools

增加：

```text
result.compare
result.rank
result.trend
result.anomaly
result.drilldown
result.explain
```

这样：

> “为什么下降？”

可以成为分析能力，而不是重新设计 SQL Generator。

---

# 二十五、Memory

建议拆成三个层次：

```text
Memory
│
├── Conversation Memory
├── Query State Memory
└── Task Memory
```

### Conversation Memory

保存用户历史对话。

### Query State Memory

保存当前查询语义。

### Task Memory

保存 Agent 当前任务执行到哪一步。

三者不要混在一起。

---

# 二十六、Task State

建议统一：

```json
{
  "task_id": "task_001",
  "conversation_id": "conv_001",
  "status": "RUNNING",
  "step": 3,
  "query_state": {},
  "pending_clarification": null,
  "plan": {},
  "tool_calls": [],
  "security": {
    "authorized": false
  },
  "result": null,
  "error": null
}
```

---

# 二十七、Agent State Machine

```text
CREATED
   ↓
UNDERSTANDING
   ↓
PLANNING
   ↓
WAITING_CLARIFICATION
   ↓
EXECUTING
   ↓
VALIDATING
   ↓
ANALYZING
   ↓
COMPLETED
```

异常状态：

```text
FAILED
DENIED
TIMEOUT
CANCELLED
```

---

# 二十八、HITL

企业场景必须支持：

```text
Agent
 ↓
发现风险
 ↓
Human Approval
 ↓
继续执行
```

典型场景：

```text
大规模导出
敏感字段
跨部门数据
高成本查询
异常 SQL
```

Task 可以进入：

```json
{
  "status": "WAITING_HUMAN",
  "reason": "SENSITIVE_DATA"
}
```

---

# 二十九、Observability

必须增加完整 Agent Trace：

```text
Trace
│
├── Task
├── Agent Step
├── Tool Call
├── Tool Result
├── Query DSL
├── SQL
├── AST
├── Permission Decision
├── DB Execution
├── Result
└── Final Answer
```

目标：

> 能完整解释 Agent 为什么得出了这个答案。

---

# 三十、Audit Log

企业环境建议保存：

```json
{
  "user_id": 1001,
  "question": "今年华东销售额是多少？",
  "query_state": {},
  "semantic_result": {},
  "query_dsl": {},
  "sql": "...",
  "authorized_sql": "...",
  "permission_result": {},
  "result": {},
  "answer": "...",
  "timestamp": "...",
  "latency": 1200
}
```

---

# 三十一、Dify 迁移路线

不要一次推翻。

## Phase 0：当前架构

```text
Dify Workflow
```

## Phase 1：增加 Agent Router

```text
Dify Workflow
 +
Agent Router
```

Agent 决定：

```text
简单查询
→ Query Tool

复杂分析
→ Analysis Tool

澄清
→ Clarification Tool
```

## Phase 2：节点 Tool 化

```text
semantic_tool
value_tool
schema_tool
query_tool
execute_tool
analysis_tool
```

Dify 原节点继续作为 Tool 内部实现。

## Phase 3：Agent Harness

```text
Agent
 ↓
Agent Harness
 ↓
Dify Tools
```

## Phase 4：独立 Runtime

```text
Agent Runtime
+
Semantic Service
+
Query Compiler
+
Security Service
+
Execution Service
+
Observability
```

Dify 可以继续作为：

```text
Prototype
Workflow
Tool Host
Business Configuration
```

而不是整个系统的核心 Runtime。

---

# 三十二、当前节点 → 新架构映射

| 当前节点 | 升级后 |
|---|---|
| Context Question Rewriter | Conversation Tool |
| Query State Merger | State Manager |
| Intent Analyzer | Agent Planner |
| Permission Fetcher | Permission Tool |
| Permission Resolver | Security Kernel |
| Schema Builder | Schema Tool |
| Semantic / Metric Resolver | Semantic Tool |
| Value Lookup | Value Tool |
| Value Semantic Resolver | Value Tool |
| Query Plan Builder | Query DSL / Plan Tool |
| SQL Generator | Query Compiler |
| SQL Validator | Compiler Guard |
| AST Parser | Security Kernel |
| Permission Engine | Security Kernel |
| SQL Executor | Execution Tool |
| Result Validator | Result Kernel |
| Result Summarizer | Analysis Tool |
| Clarification Generator | Harness HITL |
| Pending Clarification | Task State |

---

# 三十三、核心职责边界

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| Agent | 决策、规划、Tool Selection | SQL 安全 |
| Harness | 状态、工具、循环、策略 | 业务语义本身 |
| Semantic Layer | 业务语义 | SQL |
| Query DSL | 描述查询 | 数据库执行 |
| Query Compiler | DSL → SQL | 权限决策 |
| Security Kernel | 权限、安全、AST | 用户意图理解 |
| Executor | 执行 | 修改 SQL |
| Result Kernel | 校验、分析 | 修改原始数据 |
| Memory | 状态 / 历史 | 权限 |
| HITL | 人工确认 | 自动授权 |

---

# 三十四、升级实施路线

## Phase 1：稳定现有 Kernel

优先固定：

```text
Query State
Semantic Resolver
Value Resolver
Schema Builder
Query Plan
AST
Permission Engine
Result Validator
```

先固定这些模块之间的 Contract。

## Phase 2：建立 Query DSL

这是本次升级最重要的一步。

优先支持：

```text
COUNT
COUNT_DISTINCT
SUM
AVG
MIN
MAX

SCALAR
GROUPED
DETAIL
RANKING

RELATION_EXISTS
FILTER
TIME
COMPARISON
```

## Phase 3：建立 Query Compiler

实现：

```text
Query DSL
 ↓
Logical Plan
 ↓
Physical Plan
 ↓
SQL
```

逐渐降低 SQL Generator 的核心地位。

## Phase 4：Tool 化

包装：

```text
semantic_tool
value_tool
schema_tool
query_tool
execute_tool
analysis_tool
```

## Phase 5：Agent Harness

实现：

```text
State Manager
Tool Registry
Tool Executor
Planner
Execution Loop
Policy Guard
HITL
Observability
```

## Phase 6：复杂 Analytics Agent

增加：

```text
Comparison
Drilldown
Trend
Anomaly
Root Cause
Insight
```

## Phase 7：独立 Runtime

最终形成：

```text
Agent Runtime
+
Semantic Service
+
Query Compiler
+
Security Service
+
Execution Service
+
Observability
```

---

# 三十五、最终生产架构

```text
                         ┌──────────────┐
                         │   User/API   │
                         └──────┬───────┘
                                ↓
                    ┌─────────────────────┐
                    │ Enterprise Agent   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │    Agent Harness    │
                    │                     │
                    │ State / Memory      │
                    │ Planner             │
                    │ Tool Registry       │
                    │ Policy              │
                    │ Loop                │
                    │ HITL                │
                    │ Observability       │
                    └──────────┬──────────┘
                               ↓
       ┌───────────────────────┼──────────────────────┐
       ↓                       ↓                      ↓
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Semantic     │       │ Query Engine │       │ Analysis     │
│ Tools        │       │ Tools        │       │ Tools        │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ Entity       │       │ Query State  │       │ Compare      │
│ Metric       │       │ Query DSL    │       │ Rank         │
│ Dimension    │       │ Query Plan   │       │ Trend        │
│ Value        │       │ Compiler     │       │ Drilldown    │
│ Schema       │       │ SQL Renderer │       │ Explain      │
│ Relationship │       │              │       │ Insight      │
└──────┬───────┘       └──────┬───────┘       └──────┬───────┘
       │                       │                      │
       └───────────────────────┼──────────────────────┘
                               ↓
                    ┌─────────────────────┐
                    │  Security Kernel    │
                    ├─────────────────────┤
                    │ AST Parser          │
                    │ SQL Validator       │
                    │ RBAC                │
                    │ Table Permission    │
                    │ Field Permission    │
                    │ Row Permission      │
                    │ Policy Engine       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Authorized Query    │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Execution Runtime   │
                    ├─────────────────────┤
                    │ SQL                 │
                    │ DAX                 │
                    │ KQL                 │
                    │ API                 │
                    │ OLAP                │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Result Kernel       │
                    ├─────────────────────┤
                    │ Normalize           │
                    │ Validate            │
                    │ Analyze             │
                    │ Insight             │
                    └──────────┬──────────┘
                               ↓
                         Final Answer
```

---

# 三十六、最终产品定位

升级完成后，项目不应该再只是：

> Talk-to-SQL

也不应该只是：

> Talk-to-Data

更准确的定位是：

# Enterprise Analytics Agent

底层：

```text
Semantic Layer
+
Query DSL
+
Query Compiler
+
Security Kernel
+
Data Runtime
```

上层：

```text
Agent Harness
+
Analytics Agent
+
Memory
+
Tool Calling
+
HITL
+
Observability
```

最终：

```text
                 Enterprise Analytics Agent
                            │
                            ↓
                     Agent Harness
                            │
            ┌───────────────┼───────────────┐
            ↓               ↓               ↓
       Semantic         Query Engine     Analytics
         Layer             │              Engine
            │              ↓                 │
            └────────→ Query DSL ←──────────┘
                            │
                            ↓
                     Query Compiler
                            │
                            ↓
                    Security Kernel
                            │
                            ↓
                     Data Runtime
                            │
                            ↓
                       Enterprise
                          Data
```

---

# 三十七、升级核心结论

本次升级不是：

```text
Workflow → Agent
```

而应该是：

```text
Workflow
   ↓
Tools
   ↓
Agent Harness
   ↓
Enterprise Analytics Agent
```

同时：

```text
Semantic Layer
       +
Query DSL
       +
Query Compiler
       +
Security Kernel
```

成为稳定的确定性内核。

最终形成：

> **Agent 负责动态决策，Harness 负责运行时控制，Semantic Layer 负责理解企业业务，Query DSL 负责表达业务查询，Compiler 负责确定性生成执行计划，Security Kernel 负责安全边界，Execution Runtime 负责真正访问数据。**
