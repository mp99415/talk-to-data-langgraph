"""
SQL 生成节点
"""

import json
import os
import re
import time
from datetime import date, timedelta
from typing import Dict, Any
from ...tools.database import sql_query_tool
from ...llm.client import get_llm
from ...llm.prompts import get_sql_generator_prompt





def create_sql_generator_node():
    """创建 SQL GENERATOR 节点"""

    def sql_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SQL GENERATOR NODE INPUT ==========")
        print(f"query_state: {state.get('query_state')}")
        
        query_state = state.get("query_state", {})
        schema = state.get("schema", {})
        semantic_result = state.get("semantic_result", {})
        rewritten_question = state.get("rewritten_question", "")

        # ========== 最后防线：SQL 生成前强制纠正用户引用字段的 filter 值 ==========
        # 即使 semantic 节点的 schema 元数据解析失败（user_reference_fields 为空），
        # 这里也用字段名兜底集合纠正，保证 sales_id 等字段不会漏入 username/引用词等错误值
        try:
            from ..config.user_reference_config import enforce_user_reference_values
            from .filter_value_resolver import query_user_ids_by_names
            user_info_list = state.get("user_info", []) or []
            enforce_user_reference_values(
                containers=[
                    semantic_result,
                    query_state,
                    state.get("query_plan", {}) or {},
                    state.get("sql_query_plan", {}) or {},
                ],
                user_info_list=user_info_list,
                user_ref_fields=(schema or {}).get("user_reference_fields") or {},
                name_resolver=query_user_ids_by_names,
            )
        except Exception as e:
            print(f"[DEBUG][user_ref] sql_gen enforce error: {str(e)}")

        
        # 格式化 Schema 信息
        columns = schema.get("columns", {})
        schema_text = "数据库表结构：\n"
        
        if isinstance(columns, dict):
            for table, cols in columns.items():
                schema_text += f"\n表: {table}\n"
                if isinstance(cols, list):
                    for col in cols:
                        if isinstance(col, dict):
                            schema_text += f"  - {col.get('name', '')} ({col.get('type', '')})"
                            if col.get('comment'):
                                schema_text += f" - {col['comment']}"
                            schema_text += "\n"
        
        # 获取外键关系
        foreign_keys = schema.get("foreign_keys", [])
        schema_text += "\n表关系：\n"
        if isinstance(foreign_keys, list):
            for fk in foreign_keys[:20]:  # 限制数量
                if isinstance(fk, dict):
                    schema_text += f"  {fk.get('TABLE_NAME', '')}.{fk.get('COLUMN_NAME', '')} -> {fk.get('REFERENCED_TABLE_NAME', '')}.{fk.get('REFERENCED_COLUMN_NAME', '')}\n"
        
        # 调用 LLM 生成 SQL
        llm = get_llm()
        fallback_reason = None

        try:
            # 优先使用 query_plan_formatter 生成的 sql_query_plan
            sql_query_plan = state.get("sql_query_plan", {})

            print(f"[DEBUG] sql_query_plan from state: {bool(sql_query_plan)}")
            print(f"[DEBUG] checking state keys...")
            for key in state.keys():
                if 'query' in key.lower() or 'plan' in key.lower():
                    print(f"[DEBUG]   {key}: {type(state[key])}")
            if sql_query_plan:
                print(f"[DEBUG] sql_query_plan keys: {list(sql_query_plan.keys())}")
                print(f"[DEBUG] where_conditions in sql_query_plan: {sql_query_plan.get('where_conditions', [])}")

            if sql_query_plan:
                # 使用格式化后的查询计划
                query_plan = sql_query_plan
            else:
                # fallback: 自己构建 Query Plan
                query_plan = build_query_plan_from_semantic(query_state, semantic_result)

            prompt = get_sql_generator_prompt(
                rewritten_question=rewritten_question,
                query_state=json.dumps(query_state, ensure_ascii=False),
                semantic_result=json.dumps(semantic_result, ensure_ascii=False),
                query_plan=json.dumps(query_plan, ensure_ascii=False),
                schema_context=schema_text,
                permission_context=""
            )
            
            response = llm.invoke(prompt)
            content = response.content.strip()
            
            # 清理 JSON 格式
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content)

            if result.get("status") == "SUCCESS":
                sql = result.get("sql", "")
            else:
                # fallback: 使用改进后的 generate_sql 函数，传入 semantic_result
                sql = generate_sql(query_plan, semantic_result)
                fallback_reason = f"LLM返回{result.get('status')}: {result.get('error', 'Unknown error')}"
                print(f"[DEBUG] LLM SQL generation failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"[DEBUG] SQL generator error: {str(e)}")
            # fallback: 使用改进后的 generate_sql 函数，传入 semantic_result
            try:
                sql = generate_sql(query_plan, semantic_result)
                fallback_reason = f"LLM调用异常: {str(e)}"
            except ValueError as ve:
                # 如果 generate_sql 也失败了，说明缺少必要字段，返回 BLOCKED
                print(f"[DEBUG] Fallback generate_sql also failed: {str(ve)}")
                sql = ""
                fallback_reason = f"LLM异常且fallback失败: {str(ve)}"

        # ========== 统一后处理：所有生成路径（LLM 成功 / fallback / 异常兜底）都要过 ==========
        if sql:
            # 修复 LLM entity field 误映射（如 orders.sales_id → orders.id）
            sql = _correct_entity_field_misreference(sql, _extract_main_table(sql))
            # 修复客户维度列误用（如 customer_id → customers.name AS 公司）
            sql = _correct_customer_dimension(sql, semantic_result or {})
            # DETAIL 查询自动丰富展示列（让答案返回完整信息而不是只有 ID）
            sql = _enrich_detail_columns(sql, _extract_main_table(sql), semantic_result or {})

        elapsed = time.time() - start_time

        print(f"========== SQL GENERATOR NODE OUTPUT ==========")
        print(f"sql: {sql}")
        print(f"[TIMER] SQL Generator: {elapsed:.2f}s")
        print(f"==============================================\n")

        output = {"sql": sql, "node_timings": {"sql_generator": elapsed}}
        if fallback_reason:
            output["sql_generator_note"] = fallback_reason
        return output

    return sql_generator_node


def _calculate_time_range(time_value: str, current_date: date) -> Dict[str, str]:
    """轻度 Fallback：根据 time value 计算时间范围（仅作为兜底）

    仅处理简单的相对时间表达，复杂计算由 LLM 完成
    """
    if not time_value:
        return None

    value = time_value.upper().strip()

    try:
        # 今年
        if value in ["CURRENT_YEAR", "今年", "本年度", "本年"]:
            return {
                "start": f"{current_date.year}-01-01",
                "end": f"{current_date.year + 1}-01-01"
            }

        # 去年
        if value in ["PREVIOUS_YEAR", "去年", "上一年"]:
            return {
                "start": f"{current_date.year - 1}-01-01",
                "end": f"{current_date.year}-01-01"
            }

        # 今年至今
        if value in ["CURRENT_YEAR_TO_DATE", "今年至今", "到今天", "目前为止"]:
            return {
                "start": f"{current_date.year}-01-01",
                "end": current_date.strftime("%Y-%m-%d")
            }

        # 昨天
        if value in ["YESTERDAY", "昨天"]:
            yesterday = current_date - timedelta(days=1)
            return {
                "start": yesterday.strftime("%Y-%m-%d"),
                "end": current_date.strftime("%Y-%m-%d")
            }

        # 上个月
        if value in ["PREVIOUS_MONTH", "上月", "上个月"]:
            # 计算上月第一天和本月第一天
            first_day_of_month = date(current_date.year, current_date.month, 1)
            last_month_end = first_day_of_month - timedelta(days=1)
            last_month_start = date(last_month_end.year, last_month_end.month, 1)
            return {
                "start": last_month_start.strftime("%Y-%m-%d"),
                "end": first_day_of_month.strftime("%Y-%m-%d")
            }

        # 最近30天
        if value in ["LAST_30_DAYS", "最近30天"]:
            return {
                "start": (current_date - timedelta(days=29)).strftime("%Y-%m-%d"),
                "end": (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
            }

        # 最近7天
        if value in ["LAST_7_DAYS", "最近7天"]:
            return {
                "start": (current_date - timedelta(days=6)).strftime("%Y-%m-%d"),
                "end": (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
            }

        # YEAR:2025 格式
        if value.startswith("YEAR:"):
            year = int(value.replace("YEAR:", ""))
            return {
                "start": f"{year}-01-01",
                "end": f"{year + 1}-01-01"
            }

        # 纯数字年份（如 2025）
        if value.isdigit() and len(value) == 4:
            year = int(value)
            return {
                "start": f"{year}-01-01",
                "end": f"{year + 1}-01-01"
            }

    except (ValueError, TypeError):
        pass

    return None


def build_query_plan_from_semantic(query_state: Dict[str, Any], semantic_result: Dict[str, Any]) -> Dict[str, Any]:
    """根据 Query State 和 Semantic Result 构建 Query Plan"""

    # 优先使用 semantic_result 中的 resolved 映射
    if semantic_result.get("status") == "RESOLVED":
        metrics = []
        for m in semantic_result.get("metrics", []):
            if m.get("table") and m.get("field"):
                metrics.append({
                    "name": m.get("concept", ""),
                    "table": m.get("table"),
                    "field": m.get("field"),
                    "aggregation": m.get("aggregation", "SUM"),
                    "physical_value": m.get("value") or m.get("field")
                })

        # 如果没有从 semantic_result 获取到 metrics，尝试从 query_state 获取
        if not metrics:
            for m in query_state.get("metrics", []):
                if isinstance(m, dict):
                    # 尝试从 semantic_result 查找对应的 field 映射
                    concept = m.get("name", "")
                    for sm in semantic_result.get("metrics", []):
                        if sm.get("concept") == concept:
                            metrics.append({
                                "name": concept,
                                "table": sm.get("table", ""),
                                "field": sm.get("field", ""),
                                "aggregation": sm.get("aggregation", "SUM"),
                                "physical_value": sm.get("value") or sm.get("field", "")
                            })
                            break

        dimensions = []
        for d in semantic_result.get("dimensions", []):
            if d.get("table") and d.get("field"):
                dimensions.append({
                    "name": d.get("concept", ""),
                    "table": d.get("table"),
                    "field": d.get("field"),
                    "physical_value": d.get("field")
                })

        filters = []
        for f in semantic_result.get("filters", []):
            if f.get("table") and f.get("field"):
                filters.append({
                    "name": f.get("concept", ""),
                    "table": f.get("table"),
                    "field": f.get("field"),
                    "operator": f.get("operator", "="),
                    "value": f.get("value", ""),
                    "physical_value": f.get("physical_value") or f.get("value") or f.get("field")
                })

        # 处理 time - 优先使用 LLM 输出的 start 和 end
        time_obj = None
        semantic_time = semantic_result.get("time")

        # 从 semantic_result 获取 time 的 table 和 field
        time_table = ""
        time_field = ""
        time_start = ""
        time_end = ""

        if isinstance(semantic_time, dict):
            time_table = semantic_time.get("table", "")
            time_field = semantic_time.get("field", "")
            time_start = semantic_time.get("start", "")
            time_end = semantic_time.get("end", "")

        # 如果 semantic_result 没有 start/end，尝试从 query_state 获取
        if not time_start or not time_end:
            qs_time = query_state.get("time") or {}
            time_start = qs_time.get("start", "")
            time_end = qs_time.get("end", "")

        # 轻度 Fallback：如果仍然没有 start/end，尝试根据 value 计算（仅作为兜底）
        if not time_start or not time_end:
            current_date = date.today()
            time_value = ""
            if isinstance(semantic_time, dict):
                time_value = semantic_time.get("value", "")
            elif isinstance(qs_time, dict):
                time_value = qs_time.get("value", "")

            # 根据 value 尝试计算
            if time_value:
                calculated = _calculate_time_range(time_value, current_date)
                if calculated:
                    time_start = time_start or calculated.get("start", "")
                    time_end = time_end or calculated.get("end", "")

        # 如果 semantic_result 没有 table/field，从 metrics 中推断
        if not time_table or not time_field:
            if metrics:
                first_metric = metrics[0]
                time_table = first_metric.get("table", "")
                time_field = "order_date"  # 默认时间字段

        # 构建 time_obj
        if time_table and time_field and (time_start or time_end):
            time_obj = {
                "table": time_table,
                "field": time_field,
                "start": time_start,
                "end": time_end,
                "value": semantic_time.get("value", "") if semantic_time else "",
                "type": semantic_time.get("type", "YEAR") if semantic_time else "YEAR"
            }

        # 处理 events (记录存在性检查，如"是否有订单")
        events = semantic_result.get("events", [])
        for event in events:
            if event.get("event_type") == "RECORD_EXISTENCE":
                # 将事件转换为过滤条件
                table = event.get("table", "")
                field = event.get("field", "")
                operator = event.get("operator", "IS NOT NULL")
                physical_value = event.get("physical_value", "")

                filters.append({
                    "name": event.get("concept", "记录存在性"),
                    "table": table,
                    "field": field,
                    "operator": operator,
                    "value": physical_value,
                    "physical_value": physical_value,
                    "is_event": True  # 标记为事件转换的过滤条件
                })

        # 处理 relationships (表关系，用于生成 JOIN)
        relationships = semantic_result.get("relationships", [])
        required_joins = []
        tables_involved = set()

        for rel in relationships:
            source_table = rel.get("source_table", "")
            source_field = rel.get("source_field", "")
            target_table = rel.get("target_table", "")
            target_field = rel.get("target_field", "")

            if source_table and target_table:
                tables_involved.add(source_table)
                tables_involved.add(target_table)
                required_joins.append({
                    "source_table": source_table,
                    "source_field": source_field,
                    "target_table": target_table,
                    "target_field": target_field,
                    "join_type": "INNER"
                })

        # 确定主表
        tables_used = set()
        for m in metrics:
            if m.get("table"):
                tables_used.add(m["table"])
        for d in dimensions:
            if d.get("table"):
                tables_used.add(d["table"])
        for f in filters:
            if f.get("table"):
                tables_used.add(f["table"])

        # 合并 relationships 中的表
        tables_used = tables_used.union(tables_involved)

        main_table = list(tables_used)[0] if tables_used else "orders"

        return {
            "main_table": main_table,
            "required_tables": list(tables_used),
            "required_joins": required_joins,
            "entity": None,
            "metrics": metrics,
            "dimensions": dimensions,
            "filters": filters,
            "time": time_obj,  # 使用解析后的 time_obj
            "events": events,
            "ranking": None,
            "comparison": None,
            "query_shape": "GROUPED_AGGREGATE" if dimensions else "AGGREGATE",
            "limit": None
        }

    # 如果没有 resolved，返回原始 query_state
    return query_state


def generate_sql(query_state: Dict[str, Any], semantic_result: Dict[str, Any] = None) -> str:
    """根据 Query State 生成 SQL

    优先使用 semantic_result 中的 resolved 字段映射，避免依赖 LLM 推断
    支持嵌套查询（extensions.sub_query）
    """
    # 优先从 query_state 获取，如果为空则从 semantic_result 获取
    metrics = query_state.get("metrics", []) or semantic_result.get("metrics", []) if semantic_result else []
    dimensions = query_state.get("dimensions", []) or semantic_result.get("dimensions", []) if semantic_result else []
    filters = query_state.get("filters", [])
    time = query_state.get("time")
    extensions = semantic_result.get("extensions", {}) if semantic_result else {}
    sub_query = extensions.get("sub_query") if extensions else None

    select_parts = []
    where_parts = []
    group_by_parts = []
    join_parts = []

    # 构建 concept -> field 映射
    # 注意：metrics 可能有 concept 和 business_name 两个不同的名称
    concept_to_field = {}
    if semantic_result and semantic_result.get("status") == "RESOLVED":
        for m in semantic_result.get("metrics", []):
            concept = m.get("concept", "")
            business_name = m.get("business_name", "")
            field = m.get("field", "")
            if concept and field:
                concept_to_field[concept] = {
                    "field": field,
                    "table": m.get("table", ""),
                    "aggregation": m.get("aggregation", "SUM")
                }
            # 同时用 business_name 作为 key
            if business_name and field and business_name != concept:
                concept_to_field[business_name] = {
                    "field": field,
                    "table": m.get("table", ""),
                    "aggregation": m.get("aggregation", "SUM")
                }
        for d in semantic_result.get("dimensions", []):
            concept = d.get("concept", "")
            business_name = d.get("business_name", "")
            field = d.get("field", "")
            if concept and field:
                concept_to_field[concept] = {
                    "field": field,
                    "table": d.get("table", ""),
                    "aggregation": None
                }
            # 同时用 business_name 作为 key
            if business_name and field and business_name != concept:
                concept_to_field[business_name] = {
                    "field": field,
                    "table": d.get("table", ""),
                    "aggregation": None
                }

    print(f"[DEBUG] generate_sql_from_state: concept_to_field = {concept_to_field}")
    print(f"[DEBUG] generate_sql_from_state: metrics = {metrics}")

    for metric in metrics:
        if isinstance(metric, dict):
            # 优先使用 semantic_result 中的 resolved 字段
            # 注意：metric 可能有 name 或 concept 或 value 字段
            concept = metric.get("concept") or metric.get("name", "") or metric.get("value", "")
            
            # 在 concept_to_field 中查找，可能使用 name 或 value 作为 key
            resolved = concept_to_field.get(concept)
            if not resolved:
                # 尝试使用 value 字段查找
                value_key = metric.get("value", "")
                resolved = concept_to_field.get(value_key)
            
            print(f"[DEBUG] metric processing: concept={concept}, resolved={resolved}")
            
            if resolved:
                field = resolved["field"]
                agg = resolved.get("aggregation") or metric.get("aggregation") or "SUM"
                alias = metric.get("name") or metric.get("business_name", concept) or metric.get("value", "")
            else:
                # fallback: 使用 metric 本身的信息
                field = metric.get("field", "")
                agg = metric.get("aggregation") or "SUM"
                alias = metric.get("business_name", concept)

            # 聚合归一化：LLM 可能输出 "NONE"/空，指标默认按 SUM 处理
            if not str(agg).strip() or str(agg).strip().upper() in ("NONE", "NULL"):
                agg = "SUM"

            if field:
                select_parts.append(f"{agg}(`{field}`) AS `{alias}`")

    dim_fields = set()
    for dim in dimensions:
        if isinstance(dim, dict):
            # 优先使用 semantic_result 中的 resolved 字段
            # 注意：dim 可能有 name 或 concept 字段
            concept = dim.get("concept") or dim.get("name", "")
            if concept in concept_to_field:
                resolved = concept_to_field[concept]
                field = resolved["field"]
            else:
                field = dim.get("field", "")

            if field:
                select_parts.append(f"`{field}`")
                group_by_parts.append(f"`{field}`")
                dim_fields.add(field)

    # 实体显示字段：语义解析常把"公司/客户"放 entities 而非 dimensions，同样需要 SELECT + GROUP BY
    entities = semantic_result.get("entities", []) if semantic_result else []
    for ent in entities:
        if isinstance(ent, dict):
            ent_table = ent.get("table", "")
            ent_field = ent.get("field", "")
            ent_name = ent.get("concept") or ent.get("business_name", "")
            if ent_table and ent_field and ent_name and ent_field not in dim_fields:
                select_parts.append(f"`{ent_table}`.`{ent_field}` AS `{ent_name}`")
                group_by_parts.append(f"`{ent_table}`.`{ent_field}`")
                dim_fields.add(ent_field)

    if not select_parts:
        # 如果没有任何字段，返回 BLOCKED 而不是生成无效 SQL
        raise ValueError("Cannot generate SQL: no resolved fields available. Metric/Dimension fields not found in semantic_result.")

    for f in filters:
        if isinstance(f, dict):
            field = f.get("field", "")
            value = f.get("physical_value") or f.get("value", "")
            if field and value:
                where_parts.append(f"`{field}` = '{value}'")

    if time:
        field = time.get("field", "")
        start = time.get("start", "")
        end = time.get("end", "")
        if field and start and end:
            where_parts.append(f"`{field}` >= '{start}'")
            where_parts.append(f"`{field}` < '{end}'")
        elif field and time.get("value"):
            # fallback to value
            where_parts.append(f"`{field}` = '{time.get('value')}'")

    # ========== 处理嵌套查询（扩展版） ==========
    # 检查是否需要嵌套查询：查询"销售额最高的公司 X"模式
    # 这种情况下需要：
    # 1. 子查询找出"销售额最高的"公司
    # 2. 主查询计算这些公司的 X 指标
    needs_subquery = False
    sub_metric_name = ""  # 子查询的指标名（如"销售额"）
    sub_limit = 1
    
    # 从 extensions 获取子查询配置
    sub_query_config = semantic_result.get("extensions", {}).get("sub_query") if semantic_result else None
    
    # 检测是否需要隐式子查询
    # sub_query_config 只在嵌套查询检测确认后写入，其存在本身即是信号
    if sub_query_config:
        sub_metric_name = sub_query_config.get("metric", "")
        needs_subquery = True
        sub_limit = sub_query_config.get("limit", 1)
        print(f"[DEBUG] 检测到需要子查询: sub_metric={sub_metric_name}")
    
    # 获取主表（必须在子查询块之前赋值，子查询 WHERE 过滤需要引用）
    # 查询计划可能返回空 main_table，此时从指标表推导（指标表即事实表）
    main_table = query_state.get("main_table") or ""
    if not main_table:
        for m in metrics:
            if isinstance(m, dict) and m.get("table"):
                main_table = m["table"]
                break
    if not main_table:
        main_table = "orders"

    if sub_query_config and needs_subquery:
        # 获取当前指标名（用于日志）
        current_metric = metrics[0].get("concept") or metrics[0].get("name", "") if len(metrics) > 0 else ""
        print(f"[DEBUG] 处理嵌套查询: sub_metric={sub_metric_name}, current_metric={current_metric}")

        # 优先使用 sub_query_config 中已有的字段信息
        sub_metric_field = sub_query_config.get("field")
        sub_metric_agg = sub_query_config.get("aggregation", "SUM") or "SUM"
        sub_table = sub_query_config.get("table", "orders")
        sub_ranking = sub_query_config.get("ranking", "DESC") or "DESC"

        # 如果没有字段信息，尝试从 concept_to_field 查找
        if not sub_metric_field:
            for m_key, m_val in concept_to_field.items():
                if sub_metric_name in m_key or m_key in sub_metric_name:
                    sub_metric_field = m_val.get("field", "")
                    sub_metric_agg = m_val.get("aggregation", "SUM") or "SUM"
                    sub_table = m_val.get("table", "orders")
                    break

        if sub_metric_field:
            # 构建子查询
            # 时间归属：时间条件属于排序指标，优先取 sub_query.time，其次主 time
            sub_time = sub_query_config.get("time") or (semantic_result.get("time") if isinstance(semantic_result, dict) else None) or time
            sub_where = ""
            if isinstance(sub_time, dict):
                time_field = sub_time.get("field", "order_date")
                time_start = sub_time.get("start", "")
                time_end = sub_time.get("end", "")
                if time_start and time_end:
                    sub_where = f" WHERE `{time_field}` >= '{time_start}' AND `{time_field}` < '{time_end}'"

            # 子查询：找出排序指标最高/最低的实体的 customer_id
            sub_sql = f"(SELECT `customer_id` FROM `{sub_table}`{sub_where} GROUP BY `customer_id` ORDER BY {sub_metric_agg}(`{sub_metric_field}`) {sub_ranking} LIMIT {sub_limit})"

            # 将子查询添加到 WHERE 条件
            where_parts.append(f"`{main_table}`.`customer_id` IN {sub_sql}")
            print(f"[DEBUG] 子查询: {sub_sql}")

    # 构建完整的 SQL
    sql = "SELECT " + ", ".join(select_parts)
    sql += f" FROM `{main_table}`"

    # JOIN 实体表：主表与实体表不同时通过 customer_id 外键关联（含子查询场景下显示公司名称）
    joined_tables = {main_table}
    for ent in entities:
        if isinstance(ent, dict):
            ent_table = ent.get("table", "")
            if ent_table and ent_table not in joined_tables:
                sql += f" INNER JOIN `{ent_table}` ON `{main_table}`.`customer_id` = `{ent_table}`.`id`"
                joined_tables.add(ent_table)
    # 兜底：无 entities 信息但子查询要求显示公司/客户时，按硬编码关联
    if needs_subquery and sub_query_config:
        entity_info = sub_query_config.get("entity", "")
        if "customers" not in joined_tables and ("公司" in entity_info or "客户" in entity_info):
            sql += f" INNER JOIN `customers` ON `{main_table}`.`customer_id` = `customers`.`id`"
            joined_tables.add("customers")

    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    if group_by_parts:
        sql += " GROUP BY " + ", ".join(group_by_parts)

    # ========== DETAIL 查询自动丰富展示列 ==========
    # 当 SELECT 只有 entity.field（如 orders.id）时，answer 只显示 ID 不友好。
    # 自动添加业务展示列（name、amount、date 等），提升答案可读性。
    sql = _enrich_detail_columns(sql, main_table, semantic_result)

    return sql


def _extract_main_table(sql: str) -> str:
    """从 SQL 中提取主表名（FROM 后的第一个表）"""
    if not sql:
        return ""
    m = re.search(r"\bFROM\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", sql, re.IGNORECASE)
    return m.group(1) if m else ""


def _correct_entity_field_misreference(sql: str, main_table: str) -> str:
    """
    纠正 LLM 语义解析时的 entity field 误映射。

    业务背景:
      LLM semantic_resolver 有时会错误地把 entity 字段映射到 sales_id
      （如 entity "订单" 的 field 被识别为 sales_id）。
      这导致 SQL 输出的 "订单号" 实际上是销售员 ID，不是真实订单号。

    修复策略:
      根据主表，把 sales_id 替换为更合理的字段：
      - orders: sales_id → id（订单主键）
      - customers: sales_id → name（客户名称）
      - users: 不替换（sales_id 本就指销售员）

    重要: 只替换 SELECT 和 GROUP BY 子句中的字段引用，
    不能替换 WHERE 子句（WHERE sales_id = xxx 是销售员过滤，正确的）。
    """
    if not sql or not main_table:
        return sql

    # 映射规则：sales_id → 更合理的字段
    field_aliases = {
        "orders": [
                ("`orders`.`sales_id`", "`orders`.`id`"),
                ("orders.sales_id", "orders.id"),
            ],
        "customers": [
                ("`customers`.`sales_id`", "`customers`.`name`"),
                ("customers.sales_id", "customers.name"),
            ],
    }

    aliases = field_aliases.get(main_table, [])
    if not aliases:
        return sql

    # 提取 SELECT 和 GROUP BY 子句（不包含 WHERE）
    # 找到 WHERE 位置
    where_match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
    select_groupby_part = sql[:where_match.start()] if where_match else sql

    corrected_select = select_groupby_part
    for wrong, right in aliases:
        if wrong.lower() in corrected_select.lower() and right.lower() not in corrected_select.lower():
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            corrected_select = pattern.sub(right, corrected_select)

    if where_match:
        return corrected_select + sql[where_match.start():]
    return corrected_select


def _find_top_level_from(sql: str) -> int:
    """找到最外层（括号深度为 0）的 FROM 关键字位置，找不到返回 -1"""
    depth = 0
    for m in re.finditer(r"[()]|\bFROM\b", sql, re.IGNORECASE):
        tok = m.group(0)
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        elif depth == 0:  # FROM 且不在子查询内
            return m.start()
    return -1


def _correct_customer_dimension(sql: str, semantic_result: dict = None) -> str:
    """
    纠正客户维度列的误用。

    业务背景:
      问"销售额最高的公司是哪家"时，SQL 可能生成
      `orders`.`customer_id` 或 `customer_id` AS `公司` 作为展示列，
      导致答案显示客户编号（如 2006，还会被 summarizer 误读为"2006年"），
      而不是真实公司名。

    修复策略:
      只处理最外层 SELECT 列（不动 WHERE / GROUP BY / 子查询）：
      1) `customer_id` AS <业务别名(公司/客户等)> → MAX(`customers`.`name`) AS <原别名>
      2) 裸 `customer_id`（无别名）→ MAX(`customers`.`name`) AS <概念别名>
         概念别名取 semantic_result 中 entity/dimension/ranking 的 concept，缺省"公司"
      3) 维度列缺失（LLM 只生成聚合列 + 子查询过滤）→ 追加 MAX(`customers`.`name`) 列
      替换后若 SQL 没有 JOIN customers，自动注入
      INNER JOIN `customers` ON `orders`.`customer_id` = `customers`.`id`。
      用 MAX() 包裹保证在有/无 GROUP BY 及 ONLY_FULL_GROUP_BY 模式下均合法。
    """
    if not sql:
        return sql

    # 定位最外层 SELECT 列范围（到顶层 FROM 为止）
    from_pos = _find_top_level_from(sql)
    if from_pos <= 0:
        return sql
    select_clause = sql[:from_pos]
    rest = sql[from_pos:]

    has_customers_join = bool(re.search(r"\bJOIN\s+`?customers`?", sql, re.IGNORECASE))

    # 1) 带业务别名的形式（含表前缀）。
    #    完整捕获别名 token 再校验白名单，避免把 `客户编号` 误当作 `客户` 前缀匹配
    _COMPANY_ALIASES = ("公司名", "客户名", "公司名称", "客户名称", "公司", "客户")
    alias_pattern = re.compile(
        r"((?:`?[A-Za-z_][A-Za-z0-9_]*`?\s*\.\s*)?`?customer_id`?)\s+AS\s+`?([^`\s]+)`?",
        re.IGNORECASE,
    )

    def _replace_alias(m: re.Match) -> str:
        if m.group(2) in _COMPANY_ALIASES:
            return f"MAX(`customers`.`name`) AS `{m.group(2)}`"
        return m.group(0)

    select_clause = alias_pattern.sub(_replace_alias, select_clause)

    # 2) 裸 customer_id（无别名）：仅替换处于列表位置的列（紧跟 SELECT 或逗号之后），
    #    避免误伤 SUM(customer_id) 等函数内用法
    #    注意：customer_id 带非白名单别名（如 客户编号/区域）时也不动，那是查询本意
    if "customer_id" in select_clause.lower():
        # 概念别名：优先 semantic_result 的 entity/dimension/ranking concept
        alias = _find_customer_concept(semantic_result) or "公司"

        bare_pattern = re.compile(
            r"(,\s*|SELECT\s+)((?:`?[A-Za-z_][A-Za-z0-9_]*`?\s*\.\s*)?`?customer_id`?)"
            r"(?![A-Za-z0-9_])(?!\s*\()(?!(?:\s*`)?\s+AS\b)",
            re.IGNORECASE,
        )
        select_clause = bare_pattern.sub(
            lambda m: f"{m.group(1)}MAX(`customers`.`name`) AS `{alias}`", select_clause
        )

    # 3) 维度列缺失：外层 SELECT 完全没有客户维度列（既无 customers.name 也无
    #    customer_id，LLM 只生成聚合列 + 子查询过滤）→ 补一列 MAX(`customers`.`name`)，
    #    聚合安全（有无 GROUP BY 均合法）。
    #    仅当语义层确实解析出公司/客户维度时才补，避免过滤型查询被塞入无关列
    if ("customers.name" not in select_clause.replace("`", "").lower()
            and "customer_id" not in select_clause.lower()):
        concept = _find_customer_concept(semantic_result)
        if concept in ("公司", "客户", "公司名", "客户名", "公司名称", "客户名称"):
            select_clause = select_clause.rstrip() + f", MAX(`customers`.`name`) AS `{concept}` "

    # SELECT 已引用 customers.name 但 SQL 没有 JOIN customers → 注入 JOIN
    # 仅当主表是 orders 时注入（FK: orders.customer_id -> customers.id）
    if "customers.name" in select_clause.replace("`", "").lower() and not has_customers_join:
        rest = re.sub(
            r"(FROM\s+`?orders`?)",
            r"\1 INNER JOIN `customers` ON `orders`.`customer_id` = `customers`.`id`",
            rest,
            count=1,
            flags=re.IGNORECASE,
        )

    return select_clause + rest


def _find_customer_concept(semantic_result: dict) -> str:
    """从语义结果中查找公司/客户概念词（用于维度列别名）。

    查找顺序（LLM 输出不稳定，concept 可能出现在不同位置）：
      1. dimensions / entities[0].concept
      2. ranking.concept（如"公司"只出现在排名配置中，dimensions 为空）
      3. extensions.sub_query.entity
    """
    sr = semantic_result or {}
    # 1) dimensions / entities
    for key in ("dimensions", "entities"):
        items = sr.get(key) or []
        if items and isinstance(items[0], dict):
            c = (items[0].get("concept") or "").strip()
            if c:
                return c
    # 2) ranking.concept（排名型查询，dimensions 可能为空）
    ranking = sr.get("ranking")
    if isinstance(ranking, dict):
        c = (ranking.get("concept") or "").strip()
        if c:
            return c
    # 3) extensions.sub_query.entity
    ext = sr.get("extensions")
    if isinstance(ext, dict):
        sub_q = ext.get("sub_query")
        if isinstance(sub_q, dict):
            c = (sub_q.get("entity") or "").strip()
            if c:
                return c
    return ""


def _enrich_detail_columns(sql: str, main_table: str, semantic_result: dict) -> str:
    """
    当 SQL 是 DETAIL 查询（SELECT 只包含主键）时，自动添加展示列。

    例如:
      SELECT orders.id ... → 追加 amount/status/customer_id/order_date

    让 answer 直接返回订单/客户的完整信息，而不是只返回 ID。

    同时修正 LLM 语义解析时的 entity field 误映射：
      - 用户问"我的订单"，LLM 把 entity.field 误识别为 sales_id
      - 应纠正为 orders.id（订单主键）
      - 类似：用户问"我的客户"，应纠正为 customers.name（不是 sales_id）
    """
    if not sql or not semantic_result:
        return sql

    # ========== 修复 LLM entity field 误映射（任何时候都执行） ==========
    # 当 SELECT 的列是 sales_id 但别名是业务实体名（订单/客户等），
    # 说明 LLM 把"销售员"字段当成了"实体"字段。需要纠正。
    # 注意：即使含 GROUP BY / 聚合，也要先纠正字段名，否则 SQL 会用错的字段。
    sql = _correct_entity_field_misreference(sql, main_table)

    # 检查 SELECT 是否只有 1 个列且为主键
    # 简化规则：检查 SELECT 中是否含聚合函数（已经是 GROUP 模式则不增强）
    sql_upper = sql.upper()
    if "GROUP BY" in sql_upper:
        return sql
    if "SUM(" in sql_upper or "COUNT(" in sql_upper or "AVG(" in sql_upper:
        return sql
    # 检查 SELECT 列数
    select_match = re.search(r"\bSELECT\s+(.*?)\s+FROM\b", sql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return sql
    select_clause = select_match.group(1)
    # 如果 SELECT 超过 3 个列（聚合维度已足够），不增强
    # 含 AS 别名不阻止增强（别名是给 answer 看的，不影响列数判断）
    if select_clause.count(",") >= 2:
        return sql

    # 根据 main_table 推断补充列
    enrich_map = {
        "orders": ["amount", "status", "order_date", "customer_id"],
        "customers": ["name", "region"],
        "users": ["name", "username", "region"],
    }
    extra_fields = enrich_map.get(main_table, [])
    if not extra_fields:
        return sql

    # 检查 SQL 中是否已包含这些字段
    additions = []
    for f in extra_fields:
        if re.search(rf"\b{re.escape(f)}\b", sql, re.IGNORECASE):
            continue
        additions.append(f"`{f}`")
    if not additions:
        return sql
    # 注入到 SELECT 列中（使用捕获组保留 select 子句，避免 f-string 转义问题）
    new_select = select_clause + ", " + ", ".join(additions)
    new_sql = re.sub(
        r"\bSELECT\s+(.*?)\s+FROM\b",
        r"SELECT \1, " + ", ".join(additions) + " FROM",
        sql,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return new_sql


def create_sql_executor_node():
    """创建 SQL EXECUTOR 节点"""

    def executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SQL EXECUTOR NODE INPUT ==========")
        print(f"sql: {state.get('sql', '')}")
        print(f"===============================================\n")

        sql = state.get("sql", "")

        if not sql:
            return {"execution_result": []}

        db_host = os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com")
        db_name = os.getenv("DB_NAME", "talktodata")
        db_port = int(os.getenv("DB_PORT", "63888"))
        db_password = os.getenv("DB_PASSWORD")

        result = sql_query_tool.invoke({
            "db_host": db_host,
            "db_name": db_name,
            "db_port": db_port,
            "sql": sql,
            "db_password": db_password
        })

        try:
            parsed_result = json.loads(result)
        except:
            parsed_result = result

        elapsed = time.time() - start_time

        print(f"\n========== SQL EXECUTOR NODE OUTPUT ==========")
        print(f"execution_result: {str(parsed_result)[:300]}")
        print(f"[TIMER] SQL Executor: {elapsed:.2f}s")
        print(f"===============================================\n")

        return {"execution_result": parsed_result, "node_timings": {"sql_executor": elapsed}}

    return executor_node
