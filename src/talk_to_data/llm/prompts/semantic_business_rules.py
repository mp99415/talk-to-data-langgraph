"""
业务规则补充
仅包含 Schema Context 和 metadata 无法表达的语义规则
"""

BUSINESS_RULES = """
【业务语义补充规则】

=================================================
一、COUNT DISTINCT 规则
=================================================

【关键规则 - COUNT DISTINCT】
当用户问"有多少家公司/客户/供应商/经销商/门店"等统计**不同实体数量**时，必须使用 semantic_type: "count_distinct"
- "有多少家[实体]" → semantic_type: "count_distinct"
- **重要**：field 应选择对应实体的**外键字段**，而不是主键！

示例：
- "有多少家公司"（统计不同公司数量）→ field: "customer_id"（orders 表的外键）
- "有多少个客户"（统计不同客户数量）→ field: "customer_id"（orders 表的外键）
- "有多少家供应商"（统计不同供应商数量）→ field: "supplier_id"

**错误示例**：
- ❌ field: "id"（主键）→ 会统计所有订单数量
- ✅ field: "customer_id"（外键）→ 统计不同公司数量

COUNT 和 COUNT_DISTINCT 的区别：
- COUNT(*) 或 COUNT(field)：统计所有记录数，包括重复值
- COUNT(DISTINCT field)：统计不同值的数量，用于"有多少个XX"

【关键规则 - 实体显示字段】
当"公司/客户/供应商"作为 **entities（实体/显示维度）** 时，必须使用**名称字段**而不是 id：
- 问"每家公司销售额" → entities: 公司 → field: "name"（公司名称）
- 问"每家供应商销量" → entities: 供应商 → field: "name"（供应商名称）

**错误示例**：
- ❌ field: "id" → 返回 2001, 2002 等数字，不直观
- ✅ field: "name" → 返回 "杭州科技有限公司" 等名称

**entity 和 metrics 的 field 规则**：
- **entities（显示维度）** → 用名称字段（name）：直观显示公司名
- **metrics（统计指标）** → 用外键字段（customer_id）：统计不同实体数量

**示例**：
- 问题："有多少家公司"（仅统计数量，不需要显示每家公司）
  → entities: [{concept: "公司", field: "name"}]
  → metrics: [{concept: "数量", field: "customer_id", aggregation: "COUNT_DISTINCT"}]
- 问题："每家公司销售额"（需要显示每家公司）
  → entities: [{concept: "公司", field: "name"}]
  → metrics: [{concept: "销售额", field: "amount", aggregation: "SUM"}]

=================================================
二、聚合别名规则
=================================================

【关键规则 - 聚合别名】
business_name 必须完整描述指标含义，包含必要的修饰词：
- AVG 聚合 + "每笔/平均" → business_name 应包含"平均"、"每笔"等词

=================================================
三、极值查询规则
=================================================

【关键规则 - 极值查询】
当用户问"X最高是多少"或"X最低是多少"时，必须严格区分：

1. **问具体数值（使用 aggregation: MAX/MIN）**：
   - "今年销售额最高是多少" → semantic_type: "max", aggregation: "MAX"
   - "今年销售额最低是多少" → semantic_type: "min", aggregation: "MIN"
   - **不使用 ranking**，直接用聚合函数
   - business_name: "最高销售额" 或 "最低销售额"

2. **问谁排第1（使用 ranking）**：
   - "哪家公司的销售额最高" → 需要先按公司分组，再排序 → dimensions: 公司, ranking: DESC
   - "哪个地区的利润最低" → 需要先按地区分组，再排序 → dimensions: 地区, ranking: ASC

【极值关键词对照表】
| 用户问题关键词 | 正确解析 |
|-------------|---------|
| "X最高是多少" | aggregation: MAX（问具体数值） |
| "X最低是多少" | aggregation: MIN（问具体数值） |
| "哪家X的Y最高" | ranking: DESC（问谁排第1） |
| "哪家X的Y最低" | ranking: ASC（问谁排第1） |

【常见错误】
- "今年销售额最低是多少" 不能解析为 ranking + ASC
- 关键词"是多少"后面跟着具体数值时，应该用 aggregation

=================================================
四、隐含时间范围规则
=================================================

【关键规则 - 隐含时间范围】
当用户问"X最高/最低/最多/最少"等问题但没有明确时间时：
- 应该理解为"当前年度"（今年）
- 如果问题中提到了其他时间相关词（如"最近"、"上一"），按实际情况处理

示例：
- "销售额最高的公司" → 今年销售额最高的公司
- "订单量最多的客户" → 今年订单量最多的客户
- "最近销售最好的产品" → 最近30天销售最好的产品

=================================================
五、跨时间范围排名查询规则
=================================================

【关键规则 - 跨时间范围排名查询】（严格禁止）
当用户询问涉及两个不同时间段的排名查询时，必须返回 clarification！
禁止直接合并两个时间段的条件到同一 SQL！

常见模式（必须澄清）：
1. "去年X最高的公司，今年Y是多少" → clarification.required = true
2. "去年销售额最高的公司今年销售额是多少" → clarification.required = true
3. "前年第X名的公司今年表现如何" → clarification.required = true

错误解析示例：
❌ "去年销售额最高的公司今年销售额是多少" → 只解析"去年"或"今年"，忽略另一个时间段

正确解析示例：
✅ "去年销售额最高的公司今年销售额是多少" → 
   status: "PARTIAL"
   clarification: {
     "required": true,
     "question": "您是想查询：(1) 去年销售额最高的公司今年销售额是多少？ (2) 还是其他？",
     "reason": "这个问题涉及跨时间范围查询，需要先确定'去年销售额最高的公司'，再用该公司名查询'今年'的数据。这需要两步查询或子查询。"
   }

【为什么必须澄清？】
- "去年销售额最高的公司" → 需要在去年数据中找出公司名
- "今年销售额是多少" → 需要用这个公司名查询今年数据
- 这是两个不同的数据范围，不能简单地合并 WHERE 条件
- 正确做法：子查询或分两步查询

=================================================
六、时间值解析规则
=================================================

【关键规则 - 时间值解析】
当用户提到以下时间时，必须计算并输出对应的 start 和 end：

1. "今年" → value: "今年", type: "YEAR", start: "{current_year}-01-01", end: "{next_year}-01-01"
2. "去年" → value: "去年", type: "YEAR", start: "{prev_year}-01-01", end: "{current_year}-01-01"
3. "上个月" → value: "上个月", type: "MONTH", start: "{prev_month_start}", end: "{current_month_start}"
4. "最近30天" → value: "最近30天", type: "RELATIVE", start: "{last_30_days_start}", end: "{tomorrow}"
5. "昨天" → value: "Yesterday", type: "DAY", start: "{yesterday}", end: "{current_date}"
6. "今年到目前为止" → value: "今年到目前为止", type: "YTD", start: "{current_year}-01-01", end: "{current_date}"

=================================================
七、查询模式示例
=================================================

【查询模式示例】
Schema Context 和 metadata 中的示例是权威来源，这里仅作为补充参考：
1. "华东销售额" → filters: {{"field": "region", "operator": "=", "value": "EAST"}}, metrics: 销售额
2. "各地区销售额" → dimensions: 地区, metrics: 销售额
3. "哪家公司销售额最高" → dimensions: 公司, metrics: 销售额, ranking: DESC
4. "杭州科技销售额" → filters: {{"field": "company_name", "operator": "LIKE", "value": "%杭州科技%"}}, metrics: 销售额

=================================================
八、嵌套查询规则（扩展查询）
=================================================

【关键规则 - 嵌套查询识别】
当用户问"X最高的公司 Y 是多少"这类问题时，需要识别为嵌套查询：

1. **"销售额最高的公司利润是多少"**
   → 语义：先找销售额最高的公司，再查该公司利润
   → extensions.sub_query: "销售额最高的公司"
   → metrics: 利润
   → 这种情况下，把"销售额最高的公司"作为隐含的 filter 条件

2. **"利润最高的客户订单量是多少"**
   → 语义：先找利润最高的客户，再查该客户订单量
   → extensions.sub_query: "利润最高的客户"
   → metrics: 订单量

3. **"销售额前10的公司成本是多少"**
   → 语义：先找销售额前10的公司，再查这些公司的成本
   → extensions.sub_query: "销售额前10的公司"
   → metrics: 成本

【嵌套查询解析规则】
当问题包含以下模式时，添加 extensions：
- "[指标]最高的[实体] [其他指标]是多少" → 需要嵌套查询
- "[指标]最多的[实体] [其他指标]是多少" → 需要嵌套查询
- "[指标]前N的[实体] [其他指标]是多少" → 需要嵌套查询

【sub_query 字段解析规则（必须遵守）】
识别为嵌套查询后，必须根据 Schema Context 把 sub_query 的排序指标解析为物理字段：
- table：排序指标所在的物理表
- field：排序指标对应的物理字段名（必须真实存在）
- aggregation：排序指标的聚合方式（SUM/COUNT/COUNT_DISTINCT/AVG/MAX/MIN）

【时间归属规则】
- 时间词修饰排序指标时（如"今年销售额最高的公司成本"），该时间条件属于 sub_query：写入 sub_query.time（格式与主 time 相同），主 time 置为 null
- 时间词修饰主指标时（如"销售额最高的公司今年成本"），时间条件属于主查询 time，sub_query 不带 time
- 问题中没有时间词时，主 time 置为 null（系统会补全到 sub_query.time）

【ranking 规则（必须遵守）】
- 识别为嵌套查询时，主查询的 ranking 必须置为 null（排序属于 sub_query 内部）
- 禁止把排序指标（如"销售额"）写进主 metrics 或主 ranking——它不在主查询的统计范围内

【解析示例】
问题："销售额最高的公司利润是多少？"

解析结果：
```json
{
  "status": "RESOLVED",
  "extensions": {
    "sub_query": {
      "entity": "公司",
      "metric": "销售额",
      "ranking": "DESC",
      "limit": 1,
      "table": "orders",
      "field": "amount",
      "aggregation": "SUM"
    }
  },
  "entities": [],
  "metrics": [{
    "concept": "利润",
    "aggregation": "SUM",
    "field": "profit"
  }],
  "dimensions": [],
  "filters": [],
  "time": null
}
```

问题："今年销售额最高的公司成本是多少？"

解析结果（注意："今年"修饰排序指标"销售额"，时间条件放入 sub_query.time，主 time 为 null）：
```json
{
  "status": "RESOLVED",
  "extensions": {
    "sub_query": {
      "entity": "公司",
      "metric": "销售额",
      "ranking": "DESC",
      "limit": 1,
      "table": "orders",
      "field": "amount",
      "aggregation": "SUM",
      "time": {
        "table": "orders",
        "field": "order_date",
        "start": "2026-01-01",
        "end": "2027-01-01",
        "value": "CURRENT_YEAR"
      }
    }
  },
  "metrics": [{
    "concept": "成本",
    "aggregation": "SUM",
    "field": "cost"
  }],
  "dimensions": [],
  "filters": [],
  "time": null
}
```

问题："销售额最高的前10家公司成本是多少？"

解析结果：
```json
{
  "status": "RESOLVED",
  "extensions": {
    "sub_query": {
      "entity": "公司",
      "metric": "销售额",
      "ranking": "DESC",
      "limit": 10,
      "table": "orders",
      "field": "amount",
      "aggregation": "SUM"
    }
  },
  "metrics": [{
    "concept": "成本",
    "aggregation": "SUM",
    "field": "cost"
  }],
  ...
}
```

【SQL 生成时的处理】
当 semantic_result 包含 extensions.sub_query 时：
1. 在主查询的 WHERE 条件中，使用子查询过滤
2. 示例 SQL：
```sql
SELECT SUM(o.profit) AS 利润
FROM orders o
WHERE o.customer_id IN (
    SELECT customer_id FROM orders 
    WHERE YEAR(order_date) = 2026
    GROUP BY customer_id 
    ORDER BY SUM(amount) DESC
    LIMIT 1
)
```

【如果无法处理嵌套查询，退化为澄清】
如果不确定如何处理，可以返回 clarification：
- question: "您是想查询每个公司的销售额和利润，还是查询销售额最高的那家公司的利润？"
- reason: "这个问题可能需要嵌套查询或两步查询"
"""
