# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **rewriter.py - 区域切换/追加确定性规则**（`_REGION_SWITCH_RE` / `_REGION_APPEND_RE` + `_build_region_result`）
  - 切换型（"改成/换成/换到/切到/改为...华南"）→ REMOVE ENTITY + REPLACE FILTER `region='华南'`
  - 追加型（"只看/只查/仅看/只要...华东"）→ 保留实体 + REPLACE FILTER `region='华东'`
  - 指标/时间从上一轮 query_state 继承，改写问题形如"去年华南销售额是多少？"
  - 解决 LLM 在追问改写中整词丢弃"华南/华东"导致 SQL 缺失 region filter 的问题

- **main.py - 状态缓存门控**：final_answer 非空即缓存最终 state（含"仅实体无指标"查询）

- **user_reference_config.py - 用户引用条件注入**：仅在问题显式包含引用词（我/我的/他人姓名）时注入 sales_id 过滤

- **semantic.py - 人名实体兜底**：entity.value 非 customers 但精确匹配 users 时注入 sales_id filter（source=entity_user_injection）

- **rewriter 主语保护**：问题自带"我/我的"或人名"X的"时，改写不得引入上一轮实体公司名；纠正重试一次，仍失败则确定性兜底

- **intent 判定强化**：含指标词必判 DATA_QUERY；实体可疑走数据流程触发澄清；single_q + 指标词不是 ENTITY_COMPARISON

- **general_answer 占位符守卫**：检测 `[简短依据]` 等占位符原样复述时携纠正重试

- **test_cases.csv - 测试用例管理框架**
  - 支持 `run?` 列控制测试执行
  - 支持 `--rerun-untested` / `-r` 参数只执行未测试用例
  - 默认只执行 `run?=Y` 的用例
  - 执行完成后 `run?=Y` → `run?=N`
  - 自动提取 `time`、`final_result`、`sql` 列

- `semantic_prompt.py` - LLM 时间计算规则
  - 添加 13 种时间类型的精确计算规则
  - 新增 `{current_date}` 占位符，运行时传入实际日期
  - 时间对象输出添加 `start` 和 `end` 字段

- `semantic_prompt.py` - 重构为通用规则 + 业务规则
  - 拆分为 universal_prompt.py（通用规则）和 business_rules.py（业务补充）
  - 通用规则可复用到其他项目
  - 业务补充仅包含查询模式示例（Schema/metadata 可获取的信息全部动态获取）

- `summarizer_prompt.py` - NULL 值友好处理
  - 当结果为 null/None/NaN 时，生成友好提示而非直接输出技术术语
  - 提供回答模板：抱歉，该时间段暂无销售数据

- `sql_generator_prompt.py` - SQL 生成增强
  - 添加 METRIC field 完整性检查规则
  - 添加空字段 SQL 禁止规则
  - 添加 BLOCKED 触发条件明确说明

### Changed
- **时间处理通用化**
  - `resolve_time_range` 函数：移除硬编码规则，优先使用 LLM 计算的 `start/end`
  - `sql_gen.py`：`build_query_plan_from_semantic` 支持从 `semantic_result` 获取时间信息
  - `semantic_resolver` 节点：传入 `current_date` 参数

- `rewriter_prompt.py` - Prompt 压缩
  - 移除空行，减少 48% 行数

- `semantic_prompt.py` - Prompt 压缩
  - 移除空行，减少 31% 行数

### Fixed
- **多轮对话 region filter 丢弃**（Row 10/12）："改成华南"/"只看华东"追问改写后 SQL 缺失 region filter → 确定性规则处理后 SQL 含 `region='华南'`/`region='华东'`，Row 11 移除约束仍正常
- **rewriter 主语污染**：原"我的销售额是多少？"被改写成"北京云计算有限公司今年的销售额是多少？" → 主语保护后保留"我"
- **缓存门控缺失导致陈旧 state 污染多轮**：final_answer 非空才缓存修正后，含"仅实体无指标"查询的 state 也能跨轮传递
- **人名引用注入 sales_id**：semantic 实体兜底修正"李四的销售额"等他人引用
- **Row 11 多轮语义自洽**：Row 10 修复后，Row 11 "不要限制地区"能从"去年华南"正确剥离 region
- "去年销售额" 查询 SQL 缺少时间条件
- "2025年销售额" 查询缺少时间条件
- "今年到现在为止" 时间范围计算错误（应截止到今天）
- JOIN 类型从关系定义中获取（可配置）
- 时间查询（上个月/上个季度/最近30天/昨天）缺少时间条件
- **Ranking 查询解析错误**：添加 Ranking 解析规则到 semantic_prompt.py
  - "哪个区域销售额最高？" → metrics: 销售额, dimensions: 销售区域, ranking: DESC
  - "今年哪个销售区域销售额最低？" → metrics: 销售额, dimensions: 销售区域, ranking: ASC
- **Filter/Dimension 区分规则**：添加 Filter 和 Dimension 的区分规则
  - "华东销售额是多少？" → 地区作为 FILTER，不是 Dimension
  - "各地区销售额是多少？" → 地区作为 Dimension
- **公司排名查询规则**：添加"每家公司"/"前10家公司"等查询模式
- **公司-订单关系规则**：当查询涉及公司时，必须添加 relationships（JOIN customers）
- **地区过滤缺失**：修复 query_plan_builder 使用 semantic_result.filters
- **Schema Context 优化**：semantic_resolver 节点添加 foreign_keys 输出
- **Prompt 重构**：拆分为 universal_rules（通用）和 business_rules（业务补充）

### Time Processing - 折中方案
- **Prompt 增强**：`semantic_prompt.py` 时间解析规则
  - 添加强制要求：start 和 end 是必填字段
  - 添加具体示例（当前日期：{current_date}）
  - 强调 end 应该是下个时间段的第一天

- **轻度 Fallback**：`sql_gen.py` 添加 `_calculate_time_range` 函数
  - 仅作为兜底，处理简单相对时间表达
  - 支持：今年、去年、今年至今、昨天、上个月、最近30天、最近7天、YEAR:2025
  - 复杂时间计算仍由 LLM 完成

### Deprecated
- `resolve_time_range` 中的硬编码规则（已移除）

### Removed
- `get_runtime_date` 函数（不再需要）
- `resolve_time_range` 中的 Fallback 逻辑

## [1.0.0] - 2026-09-24

### Added
- Initial release
- Talk to Data Enterprise 核心功能
