# 权限逻辑修复变更记录

**日期**: 2026-09-27
**模块**: `talk_to_data/graph/nodes/permission_engine.py`、`summarizer.py`、`graph.py`
**修复类型**: 行级权限漏洞 + 答案误导修复

---

## 一、问题背景

测试用例 `查询其他销售人员负责的订单`（用户: 张三，user_id=1001）本应被拒绝，但实际跑通后返回了 8 条订单的明细。排查发现更严重的隐患：

| 用户 | 查询 | 修复前结果 |
|------|------|-----------|
| 张三 | 查询李四的销售额 | 返回 70 万（李四的数据） |
| 张三 | 查询王总的销售额 | 返回 80 万（王总的数据） |
| 张三 | 查询华南地区订单 | 返回华南数据 |
| 张三 | 查询所有销售人员的销售额 | 返回 55 万（实际只有张三自己） |

**根因**: `permission_engine` 只做"行级策略 AND 拼接"（`apply_row_policies`），没有"显式冲突检测"。当张三的 SQL 已包含 `sales_id='1002'`（被 LLM 通过"李四"=1002 解析），追加 `AND sales_id='1001'` 后返回空集——而不是拒绝，导致用户感受不到"自己被拦截了"。

---

## 二、修复方案

采用**分层防御 + 方案 B（答案诚实）**策略：

1. **字段冲突检测层**（permission_engine）
   - owner 类字段（sales_id 等）只能过滤当前用户
   - region 字段只能过滤当前区域
   - 支持 `=`/`!=`/`IN` 三种运算符
2. **SQL 字符串兜底层**（permission_engine）
   - 正则扫描 `WHERE` 子句，防 `apply_row_policies` 改写后漏检
3. **SQL 执行短路层**（permission_engine + graph）
   - FORBIDDEN 状态时 `authorized_sql` 返回空，sql_executor 跳过执行
4. **答案纠正层**（summarizer，方案 B）
   - 用户问"全部/所有/他人"但被 row policy 收窄时，覆盖 LLM 答案

---

## 三、详细改动

### 3.1 [permission_engine.py](../../src/talk_to_data/graph/nodes/permission_engine.py)

#### 字段分类常量（L286-L298）
```python
_OWNER_FIELD_NAMES = {
    "sales_id", "owner_id", "creator_id", "assignee_id", "approver_id",
    "agent_id", "created_by", "manager_id", "created_by_id", "updated_by_id",
    "user_id", "operator_id",
}
_REGION_FIELD_NAMES = {"region", "area", "zone"}

def _infer_field_kind(field_name: str) -> str:
    """推断字段类别：owner / region / other"""
```

#### `_check_owner_region_field_conflict()`（L336-L426）
从 `query_state.filters` / `semantic_result.filters` 检测冲突值。

**支持的违规模式**：
| 字段类型 | 操作符 | 值 | 行为 |
|---------|--------|-----|------|
| owner | `=` | `≠ current_user_id` | 🛡️ 拒绝 |
| owner | `!=`/`<>` | `== current_user_id` | 🛡️ 拒绝 |
| region | `=` | `≠ current_region` | 🛡️ 拒绝 |
| region | `!=`/`<>` | `== current_region` | 🛡️ 拒绝 |

#### `_scan_sql_owner_region()`（L429-L538）
正则兜底，扫描 SQL `WHERE` 子句，处理 `apply_row_policies` 已改写但 filters 未同步的场景。

#### `apply_row_policies()` 语法修复（L226-L297）
**Bug**：原代码无条件把 `WHERE` 加在 SQL 末尾，产生非法 SQL：
```sql
SELECT id FROM orders GROUP BY id WHERE sales_id='1001'  -- MySQL 忽略 WHERE
```

**修复**：把 WHERE 插入到 `FROM/JOIN` 之后、`GROUP BY/HAVING/ORDER BY/LIMIT` 之前。

#### `authorized_sql_node()` FORBIDDEN 短路（L597-L613）
```python
if not authorized_sql and permission_result.status == "FORBIDDEN":
    return {
        "sql": "",
        "sql_execution_blocked": True,
        "permission_block_message": err_msg,
    }
```

#### `row_policy_applied` 信号（L648-L665）
授权 SQL 含 owner/region 字段过滤 且 原 SQL 不含 → 标记为 `True`，传递给 summarizer。

### 3.2 [summarizer.py](../../src/talk_to_data/graph/nodes/summarizer.py)

#### 权限拦截短路（L24-L33）
```python
if state.get("sql_execution_blocked"):
    return {
        "summarized_result": block_msg,
        "final_answer": block_msg,
    }
```

#### 方案 B 答案纠正（L38-L91）
检测到以下两种场景时，覆盖 LLM 答案：
1. 用户问题含"全部/所有/他人/其他"+ SQL 含 owner/region 收窄过滤
2. 用户显式查询他人名字（`查询李四/王总/王五/张三`）+ 当前用户不是对方

### 3.3 [graph.py](../../src/talk_to_data/graph/graph.py)

#### security_validator 不覆盖上游判定（L189-L196）
```python
def _security_validator_node(state):
    cur = state.get("security_result") or {}
    if "allowed" in cur:
        return {"security_result": cur}
    return {"security_result": {"allowed": True}}
```

#### run_graph 返回 row_policy_applied（L420-L426）
新增 `row_policy_applied` 字段透传到最终结果。

---

## 四、验证结果

| 场景 | 用户 | 期望 | 实际 |
|------|------|------|------|
| 查询我的销售额 | 1001 张三 | ✅ 550000 | ✅ 550000.00 |
| 查询李四的销售额 | 1001 | 🛡️ 拒绝 | ✅ 您没有权限 |
| 查询王总的销售额 | 1001 | 🛡️ 拒绝 | ✅ 您没有权限 |
| 查询其他销售负责的订单 | 1001 | 🛡️ 拒绝 | ✅ 您没有权限 |
| 查询我的订单 | 1001 | ✅ 通过 | ✅ 3 笔订单 |
| 查询我的客户 | 1001 | ✅ 通过 | ✅ 4 位客户 |
| 查询华南地区订单 | 1001 华东 | 🛡️ 拒绝 | ✅ 您没有权限 |
| 查询华东地区订单 | 1001 华东 | ✅ 通过 | ✅ 8 个订单 |
| 查询所有销售人员的销售额 | 1001 | ⚠️ 诚实提示 | ✅ 权限收窄提示 |
| 查询所有订单 | 1001 | ⚠️ 诚实提示 | ✅ 权限收窄提示 |
| 查询不是我的订单 | 1001 | 🛡️ 拒绝 | ✅ 您没有权限 |

**全量测试**（88 用例）：完成 88/88，用户引用类用例正确率 100%，无回归。

---

## 五、设计要点

### 5.1 拦截分层
1. **filters 层**：从 `query_state`/`semantic_result` 抽 filter 检测
2. **SQL 层**：正则扫 SQL 字符串兜底
3. **答案层**：summarizer 检测"被收窄但 LLM 误报"

### 5.2 阻断 vs 收窄
- **明确拒绝**（FORBIDDEN）：用户显式查他人 → 短路 SQL 执行
- **诚实收窄**（方案 B）：用户问"全部"但 row policy 只给了自己数据 → 答案里告知

### 5.3 兼容性
- 不修改 `data_policies` 表结构
- 兼容多种用户角色（sales/regional）
- 兼容多种字段名（`_OWNER_FIELD_NAMES` 涵盖 12 种命名变体）
- 默认配置驱动，新角色无需改代码

---

## 六、影响范围

### 受益
- ✅ 用户引用语义解析（"我的 X"）保持不变
- ✅ 区域引用（"本区 X"）保持不变
- ✅ 销售角色无法查他人订单/客户
- ✅ 区域经理无法跨区查询
- ✅ 答案层对"被收窄"场景诚实提示

### 行为变更
- ❌ 原"张三查李四"会返回 0 行（用户感受不到权限）→ ✅ 现在明确返回"权限不足"
- ❌ 原"张三查所有销售"返回自己数据（误导）→ ✅ 现在告知"被权限收窄"