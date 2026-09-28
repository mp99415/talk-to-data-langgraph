"""
查询计划构建器节点
"""

import json
import time
from datetime import date
from typing import Dict, Any, List, Optional


# ============================================================
# 基础工具函数
# ============================================================

def resolve_filter_values(filters: List[Dict]) -> List[Dict]:
    """解析 filters 中的 business_value -> physical_value
    
    这个函数在 query_plan_builder 中直接调用，
    避免依赖 LangGraph 状态传递问题
    """
    if not filters:
        return filters
    
    # 收集需要解析的业务值
    business_values_to_resolve = []
    for f in filters:
        value = f.get("value", "")
        if not value:
            continue
        # 跳过已经是物理值的
        if value.isdigit() or "-" in value or "/" in value:
            continue
        if value not in business_values_to_resolve:
            business_values_to_resolve.append(value)
    
    if not business_values_to_resolve:
        return filters
    
    # 查询数据库
    try:
        import pymysql
        import os
        
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com"),
            port=int(os.getenv("DB_PORT", "22636")),
            user="root",
            password=os.getenv("DB_PASSWORD", "Smic!!57o"),
            database=os.getenv("DB_NAME", "talktodata"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        
        placeholders = ", ".join(["%s"] * len(business_values_to_resolve))
        sql = f"""
            SELECT a.alias, dv.physical_value, dim.table_name, dim.field_name
            FROM semantic_value_aliases a
            JOIN semantic_dimension_values dv ON a.value_id = dv.id
            JOIN semantic_dimensions dim ON dv.dimension_id = dim.id
            WHERE a.alias IN ({placeholders})
        """
        
        with conn.cursor() as cursor:
            cursor.execute(sql, business_values_to_resolve)
            results = cursor.fetchall()
        
        conn.close()
        
        # 构建映射
        value_mapping = {}
        for row in results:
            alias = row.get("alias", "")
            physical_value = row.get("physical_value", "")
            if alias and physical_value:
                value_mapping[alias] = {
                    "physical_value": physical_value,
                    "table": row.get("table_name", ""),
                    "field": row.get("field_name", "")
                }
        
        print(f"[DEBUG] resolve_filter_values: value_mapping = {value_mapping}")
        
        # 解析 filters
        resolved = []
        for f in filters:
            value = f.get("value", "")
            resolved_f = f.copy()
            
            if value in value_mapping:
                mapping = value_mapping[value]
                resolved_f["physical_value"] = mapping["physical_value"]
                # 补充 table 和 field
                if not resolved_f.get("table"):
                    resolved_f["table"] = mapping.get("table", "")
                if not resolved_f.get("field"):
                    resolved_f["field"] = mapping.get("field", "")
                print(f"[DEBUG] resolve_filter_values: resolved {value} -> {mapping['physical_value']}")
            else:
                resolved_f["physical_value"] = value
            
            # 字段名纠错：LLM 偶发把实体名 filter 的 field 映射错（field='customer_id', value='杭州科技' → 应该是 field='name'）
            ffield = resolved_f.get("field", "")
            fvalue = str(resolved_f.get("physical_value", ""))
            if ffield in ("customer_id", "id") and not fvalue.replace("%", "").isdigit():
                resolved_f["field"] = "name"
                # name 列属于 customers 表（orders 没有 name 列，否则触发 UNKNOWN_FIELD）
                resolved_f["table"] = "customers"
                if not fvalue.startswith("%") and not fvalue.endswith("%"):
                    resolved_f["physical_value"] = f"%{fvalue}%"
                    resolved_f["operator"] = "LIKE"
                print(f"[DEBUG] resolve_filter_values 字段纠错: {ffield} -> name")
            
            resolved.append(resolved_f)
        
        return resolved
        
    except Exception as e:
        print(f"[ERROR] resolve_filter_values: {str(e)}")
        return filters


def safe_json(value, default=None):
    """安全解析JSON"""
    if value is None:
        return default

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default

        try:
            return json.loads(text)
        except Exception:
            return default

    return default


def clean_text(value):
    """清理文本"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def as_dict(value):
    """转换为字典"""
    value = safe_json(value, {})
    return value if isinstance(value, dict) else {}


def as_list(value):
    """转换为列表"""
    value = safe_json(value, [])

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        for key in ("items", "records", "filters", "resolved_filters",
                    "events", "dimensions", "metrics", "relationships"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate

    return []


def unique_preserve(items):
    """去重保留顺序"""
    result = []
    seen = set()

    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


# ============================================================
# Schema Context 处理
# ============================================================

def normalize_schema_context(schema_context):
    """标准化 Schema Context"""
    schema = as_dict(schema_context)

    tables = schema.get("tables", {})
    if not isinstance(tables, dict):
        tables = {}

    relationships = schema.get("relationships", [])
    if not isinstance(relationships, list):
        relationships = []

    visible_fields = schema.get("visible_fields", {})
    if not isinstance(visible_fields, dict):
        visible_fields = {}

    return {
        "tables": tables,
        "relationships": relationships,
        "visible_fields": visible_fields,
        "metadata": schema.get("metadata", {}),
        "status": schema.get("status", ""),
        "version": schema.get("version")
    }


def table_exists(schema, table_name):
    """检查表是否存在"""
    table_name = clean_text(table_name)
    if not table_name:
        return False
    return table_name in schema.get("tables", {})


def field_exists(schema, table_name, field_name):
    """检查字段是否存在"""
    table_name = clean_text(table_name)
    field_name = clean_text(field_name)

    if not table_name or not field_name:
        return False

    visible_fields = schema.get("visible_fields", {})
    if not isinstance(visible_fields, dict):
        return False

    table_fields = visible_fields.get(table_name, [])
    if not isinstance(table_fields, list):
        return False

    for field in table_fields:
        if isinstance(field, dict) and clean_text(field.get("name")) == field_name:
            return True

    return False


def get_field_schema(schema, table_name, field_name):
    """获取字段Schema"""
    table_name = clean_text(table_name)
    field_name = clean_text(field_name)

    visible_fields = schema.get("visible_fields", {})
    table_fields = visible_fields.get(table_name, [])

    if isinstance(table_fields, list):
        for field in table_fields:
            if isinstance(field, dict) and clean_text(field.get("name")) == field_name:
                return field

    return {}


# ============================================================
# Main Table 推断
# ============================================================

def infer_main_table(semantic, query_state, schema):
    """推断主表"""
    entity = semantic.get("entities", [])

    if isinstance(entity, list):
        for item in entity:
            if not isinstance(item, dict):
                continue
            table = clean_text(item.get("table"))
            if table and table_exists(schema, table):
                return table

    metrics = semantic.get("metrics", [])
    if isinstance(metrics, list):
        for item in metrics:
            if not isinstance(item, dict):
                continue
            table = clean_text(item.get("table"))
            if table and table_exists(schema, table):
                return table

    dimensions = semantic.get("dimensions", [])
    if isinstance(dimensions, list):
        for item in dimensions:
            if not isinstance(item, dict):
                continue
            table = clean_text(item.get("table"))
            if table and table_exists(schema, table):
                return table

    return ""


# ============================================================
# Entity 构建
# ============================================================

def build_entity(semantic):
    """构建 Entity"""
    entities = semantic.get("entities", [])
    if not isinstance(entities, list):
        return {}

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        table = clean_text(entity.get("table"))
        field = clean_text(entity.get("field"))

        if not table or not field:
            continue

        return {
            "business_name": entity.get("business_name", ""),
            "concept": entity.get("concept", ""),
            "field": field,
            "match_type": entity.get("match_type", ""),
            "table": table,
            "value": entity.get("value", "")
        }

    return {}


# ============================================================
# Metrics 构建
# ============================================================

def build_metrics(semantic):
    """构建 Metrics"""
    metrics = semantic.get("metrics", [])
    if not isinstance(metrics, list):
        return []

    result = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue

        table = clean_text(metric.get("table"))
        field = clean_text(metric.get("field"))

        if not table or not field:
            continue

        # 优先使用 aggregation，否则 fallback 到 semantic_type
        aggregation = clean_text(metric.get("aggregation")).upper()
        if not aggregation:
            # Fallback: 从 semantic_type 获取
            semantic_type = clean_text(metric.get("semantic_type")).upper()
            if semantic_type:
                # semantic_type 到 aggregation 的映射
                type_to_agg = {
                    "SUM": "SUM",
                    "COUNT": "COUNT",
                    "COUNT_DISTINCT": "COUNT_DISTINCT",
                    "AVG": "AVG",
                    "MAX": "MAX",
                    "MIN": "MIN",
                    "NONE": "NONE",
                }
                aggregation = type_to_agg.get(semantic_type, "SUM")
            else:
                aggregation = "SUM"

        result.append({
            "aggregation": aggregation,
            "alias": metric.get("business_name", metric.get("concept", "")),
            "business_name": metric.get("business_name", ""),
            "concept": metric.get("concept", ""),
            "field": field,
            "match_type": metric.get("match_type", ""),
            "semantic_type": metric.get("semantic_type", ""),
            "table": table
        })

    return result


# ============================================================
# Dimensions 构建
# ============================================================

def build_dimensions(semantic):
    """构建 Dimensions
    
    优先从 dimensions 获取，如果为空则从 entities 获取
    （LLM 可能把维度解析为 entity）
    """
    dimensions = semantic.get("dimensions", [])
    entities = semantic.get("entities", [])
    
    result = []
    
    # 首先处理 dimensions
    if isinstance(dimensions, list):
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue

            table = clean_text(dimension.get("table"))
            field = clean_text(dimension.get("field"))

            if not table or not field:
                continue

            result.append({
                "business_name": dimension.get("business_name", ""),
                "concept": dimension.get("concept", ""),
                "field": field,
                "match_type": dimension.get("match_type", ""),
                "semantic_type": dimension.get("semantic_type", ""),
                "table": table
            })
    
    # 如果 dimensions 为空，从 entities 获取
    if not result and isinstance(entities, list):
        for entity in entities:
            if not isinstance(entity, dict):
                continue
                
            # 检查是否是可作为维度的实体（如地区、公司、客户等）
            concept = clean_text(entity.get("concept", ""))
            table = clean_text(entity.get("table"))
            field = clean_text(entity.get("field"))
            entity_value = clean_text(entity.get("value", ""))
            
            # 判断 entity.value 是否是具体的 filter value
            # 具体的 filter value 通常是短文本（如"华东"、"华南"、"杭州"等）
            # 通用概念（如"销售区域"、"客户"、"公司"）应该作为 dimension
            is_concrete_value = (
                entity_value and 
                len(entity_value) <= 10 and  # 具体值通常较短
                entity_value not in ['销售区域', '客户', '公司', '供应商', '产品', '类别', '区域', '部门']  # 不是通用概念
            )
            
            # 如果 entity 有具体的 filter value，跳过（这是 filter，不是 dimension）
            if is_concrete_value:
                continue
            
            # 否则，考虑作为 dimension
            if table and field and concept:
                # 检查是否是维度类型的 entity（如 region、company、customer 等）
                dimension_indicators = [
                    'region', 'area', 'zone', 'company', 'customer', 
                    'supplier', 'product', 'category', '部门', '地区',
                    '区域', '公司', '客户', '供应商', '产品', '类别',
                    '销售区域', '销售'
                ]
                if any(ind in concept.lower() for ind in dimension_indicators):
                    result.append({
                        "business_name": entity.get("business_name", ""),
                        "concept": concept,
                        "field": field,
                        "match_type": entity.get("match_type", ""),
                        "semantic_type": "dimension",
                        "table": table
                    })

    return result


# ============================================================
# Group By 构建
# ============================================================

def build_group_by(dimensions):
    """构建 Group By"""
    result = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue

        table = clean_text(dimension.get("table"))
        field = clean_text(dimension.get("field"))

        if not table or not field:
            continue

        result.append({
            "business_name": dimension.get("business_name", ""),
            "concept": dimension.get("concept", ""),
            "field": field,
            "table": table
        })

    return unique_preserve(result)


# ============================================================
# Filters 构建
# ============================================================

def normalize_resolved_value(item):
    """标准化已解析的值"""
    if not isinstance(item, dict):
        return {
            "business_value": None,
            "physical_value": None,
            "physical_value_resolved": False
        }

    business_value = item.get("business_value")
    if business_value is None:
        business_value = item.get("user_value")
    if business_value is None:
        business_value = item.get("value")

    physical_value = item.get("physical_value")
    if physical_value is None:
        physical_value = item.get("physicalValue")
    if physical_value is None:
        physical_value = item.get("resolved_value")
    if physical_value is None:
        physical_value = item.get("resolvedValue")

    physical_exists = (
        physical_value is not None
        and clean_text(physical_value) != ""
    )

    explicit_resolved = item.get("physical_value_resolved")
    if explicit_resolved is False:
        physical_exists = False

    return {
        "business_value": business_value,
        "physical_value": physical_value,
        "physical_value_resolved": physical_exists
    }


def extract_resolved_filter_list(resolved_filters):
    """提取已解析的过滤器列表"""
    value = safe_json(resolved_filters, [])

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        for key in ("resolved_filters", "filters", "items", "records"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate

    return []


def build_filters(resolved_filters):
    """构建 Filters

    接收 merged filters（resolved + unresolved）。
    unresolved filter (physical_value_resolved=False) 自动转为 LIKE 模糊查询，
    避免丢弃导致查询返回所有数据。
    """
    items = extract_resolved_filter_list(resolved_filters)
    result = []

    for item in items:
        if not isinstance(item, dict):
            continue

        table = clean_text(item.get("table"))
        field = clean_text(item.get("field"))

        if not table or not field:
            continue

        # unresolved filter：物理值未在 metadata 中找到，转为 LIKE 模糊查询
        if item.get("physical_value_resolved") is False:
            raw_value = item.get("value") or item.get("business_value") or ""
            if raw_value and field:
                result.append({
                    "business_field": item.get("business_field", ""),
                    "table": table,
                    "field": field,
                    "operator": "LIKE",
                    "business_value": raw_value,
                    "physical_value": f"%{raw_value}%",
                    "semantic_type": item.get("semantic_type", ""),
                    "match_type": "UNRESOLVED_LIKE",
                    "physical_value_resolved": False,
                    "source_type": item.get("source_type", ""),
                    "source_event": item.get("source_event")
                })
            continue

        normalized = normalize_resolved_value(item)

        result.append({
            "business_field": item.get("business_field", ""),
            "table": table,
            "field": field,
            "operator": item.get("operator", "="),
            "business_value": normalized["business_value"],
            "physical_value": normalized["physical_value"],
            "semantic_type": item.get("semantic_type", ""),
            "match_type": item.get("match_type", ""),
            "physical_value_resolved": normalized["physical_value_resolved"],
            "source_type": item.get("source_type", ""),
            "source_event": item.get("source_event")
        })

    return result


# ============================================================
# Time 构建
# ============================================================

def resolve_time_range(time_obj):
    """解析时间范围

    直接使用 LLM 输出的 start 和 end，不做额外计算
    如果 LLM 没有输出 start/end，返回 None
    """
    if not isinstance(time_obj, dict):
        return None

    start = clean_text(time_obj.get("start"))
    end = clean_text(time_obj.get("end"))

    if start and end:
        return {
            "type": time_obj.get("type", "") or "CUSTOM",
            "value": time_obj.get("value", "") or "CUSTOM",
            "start": start,
            "end": end
        }

    # LLM 没有输出 start/end，返回 None（由上游处理错误）
    return None


def _find_time_dimension(metadata, metrics):
    """从 metadata.semantic_dimensions 中查找时间维度

    查找逻辑：
    1. 优先查找 dimension_type='TIME' 的维度
    2. 如果没有，查找包含 'time'、'date' 关键词的维度
    3. 返回找到的第一个时间维度
    """
    if not metadata:
        return None

    dims = metadata.get("semantic_dimensions", [])
    
    # 1. 优先查找 dimension_type='TIME' 的维度
    for dim in dims:
        dim_type = dim.get("dimension_type", "").upper()
        if dim_type == "TIME":
            return dim
    
    # 2. 查找包含 'time'、'date' 关键词的维度
    keywords = ["time", "date", "时间", "日期"]
    for dim in dims:
        dim_name = dim.get("dimension_name", "").lower()
        dim_code = dim.get("dimension_code", "").lower()
        for kw in keywords:
            if kw in dim_name or kw in dim_code:
                return dim
    
    return None


def build_time(semantic, query_state=None, metadata=None):
    """构建 Time

    优先从 semantic_result 获取，如果 semantic_result 没有，则从 query_state 获取
    如果 time_obj 中没有 field/table，则从 metadata.semantic_dimensions 中查找时间维度
    """
    print(f"[DEBUG] build_time called with semantic.time={semantic.get('time')}, query_state.time={query_state.get('time') if query_state else None}")
    time_obj = semantic.get("time")

    # 如果 semantic_result 没有 time，尝试从 query_state 获取
    if not isinstance(time_obj, dict) and query_state:
        qs_time = query_state.get("time")
        if isinstance(qs_time, dict):
            time_obj = qs_time

    if not isinstance(time_obj, dict):
        return None

    # 优先使用 LLM 已经计算好的 start 和 end
    start = clean_text(time_obj.get("start"))
    end = clean_text(time_obj.get("end"))

    if start and end:
        # 获取 field 和 table
        # 优先使用 LLM 返回的，否则从 metadata.semantic_dimensions 中查找时间维度
        field = time_obj.get("field", "")
        table = time_obj.get("table", "")
        
        if not field or not table:
            # 从 metadata 中查找时间维度
            time_dimension = _find_time_dimension(metadata, semantic.get("metrics", []))
            if time_dimension:
                field = field or time_dimension.get("field_name", "order_date")
                table = table or time_dimension.get("table_name", "orders")
            else:
                # 最后 fallback
                field = field or "order_date"
                table = table or "orders"
        
        return {
            "concept": time_obj.get("concept", "时间"),
            "end": end,
            "field": field,
            "match_type": time_obj.get("match_type", "DEFAULT"),
            "semantic_type": time_obj.get("semantic_type", "YEAR"),
            "start": start,
            "table": table,
            "type": time_obj.get("type", "YEAR"),
            "value": time_obj.get("value", "")
        }

    # Fallback：如果 LLM 没有输出 start/end，使用 resolve_time_range
    resolved = resolve_time_range(time_obj)
    if not resolved:
        # 无法解析时间，返回 None（由上游处理错误）
        return None

    # 获取 field 和 table
    field = time_obj.get("field", "")
    table = time_obj.get("table", "")
    
    if not field or not table:
        # 从 metadata 中查找时间维度
        time_dimension = _find_time_dimension(metadata, semantic.get("metrics", []))
        if time_dimension:
            field = field or time_dimension.get("field_name", "order_date")
            table = table or time_dimension.get("table_name", "orders")
        else:
            # 最后 fallback
            field = field or "order_date"
            table = table or "orders"

    return {
        "concept": time_obj.get("concept", "时间"),
        "end": resolved["end"],
        "field": field,
        "match_type": time_obj.get("match_type", "DEFAULT"),
        "semantic_type": time_obj.get("semantic_type", "YEAR"),
        "start": resolved["start"],
        "table": table,
        "type": resolved["type"],
        "value": resolved["value"]
    }


# ============================================================
# Ranking 构建
# ============================================================

def build_ranking(semantic):
    """构建 Ranking"""
    ranking = semantic.get("ranking")
    if not isinstance(ranking, dict):
        return {
            "direction": "",
            "type": "",
            "metric": "",
            "limit": 0,
            "value": ""
        }

    # 获取 limit，确保是整数
    limit_value = ranking.get("limit")
    if isinstance(limit_value, int) and limit_value > 0:
        limit = limit_value
    elif isinstance(limit_value, str):
        try:
            limit = int(limit_value)
        except:
            limit = 0
    else:
        limit = 0

    return {
        "direction": ranking.get("direction", "") or ranking.get("order", ""),
        "type": ranking.get("type", ""),
        "metric": ranking.get("metric", ""),
        "limit": limit,
        "value": ranking.get("value", "")
    }


# ============================================================
# Comparison 构建
# ============================================================

def build_comparison(semantic):
    """构建 Comparison"""
    comparison = semantic.get("comparison")
    if not isinstance(comparison, dict):
        return {
            "type": "",
            "value": ""
        }

    return {
        "type": comparison.get("type", ""),
        "value": comparison.get("value", "")
    }


# ============================================================
# Events 构建
# ============================================================

def normalize_event_value(item):
    """标准化事件值"""
    if not isinstance(item, dict):
        return {
            "business_value": None,
            "physical_value": None,
            "physical_value_resolved": False
        }

    business_value = item.get("business_value")
    if business_value is None:
        business_value = item.get("user_value")
    if business_value is None:
        business_value = item.get("value")

    physical_value = item.get("physical_value")
    if physical_value is None:
        physical_value = item.get("physicalValue")
    if physical_value is None:
        physical_value = item.get("resolved_value")
    if physical_value is None:
        physical_value = item.get("resolvedValue")

    physical_exists = (
        physical_value is not None
        and clean_text(physical_value) != ""
    )

    if item.get("physical_value_resolved") is False:
        physical_exists = False

    return {
        "business_value": business_value,
        "physical_value": physical_value,
        "physical_value_resolved": physical_exists
    }


def build_events(semantic, schema_context, resolved_filters):
    """构建 Events"""
    semantic = as_dict(semantic)
    schema = normalize_schema_context(schema_context)
    events = semantic.get("events", [])

    if not isinstance(events, list):
        return []

    result = []
    resolved_filters_list = extract_resolved_filter_list(resolved_filters)

    for event in events:
        if not isinstance(event, dict):
            continue

        concept = clean_text(event.get("concept"))
        table = clean_text(event.get("table"))
        field = clean_text(event.get("field"))
        event_type = clean_text(event.get("event_type")).upper()

        if not concept or not table:
            continue

        # STATUS_EVENT
        if event_type == "STATUS_EVENT":
            resolved_filter = find_resolved_filter_for_event(event, resolved_filters_list)
            if resolved_filter is None:
                continue

            normalized = normalize_event_value(resolved_filter)
            result.append({
                "concept": concept,
                "event_type": "STATUS_EVENT",
                "table": table,
                "field": field,
                "business_value": normalized["business_value"],
                "physical_value": normalized["physical_value"],
                "physical_value_resolved": normalized["physical_value_resolved"],
                "execution": "FILTER"
            })
            continue

        # RECORD_EXISTENCE
        if event_type == "RECORD_EXISTENCE":
            result.append({
                "concept": concept,
                "event_type": "RECORD_EXISTENCE",
                "table": table,
                "field": field,
                "business_value": event.get("business_value", event.get("value", "")),
                "physical_value": None,
                "physical_value_resolved": True,
                "execution": "JOIN"
            })
            continue

        # 其他事件
        result.append({
            "concept": concept,
            "event_type": event_type,
            "table": table,
            "field": field,
            "business_value": event.get("business_value", event.get("value", "")),
            "physical_value": event.get("physical_value"),
            "physical_value_resolved": event.get("physical_value") is not None,
            "execution": "FILTER" if field else "JOIN"
        })

    return result


def normalize_match_text(value):
    """标准化匹配文本"""
    if value is None:
        return ""
    text = clean_text(value)
    text = text.strip("\"'""''")
    return text


def source_event_matches(source_event, event):
    """检查源事件是否匹配"""
    if not isinstance(source_event, dict) or not isinstance(event, dict):
        return False

    source_concept = normalize_match_text(source_event.get("concept"))
    event_concept = normalize_match_text(event.get("concept"))
    source_type = normalize_match_text(source_event.get("event_type"))
    event_type = normalize_match_text(event.get("event_type"))

    if source_concept and event_concept and source_concept == event_concept:
        if not source_type or not event_type or source_type == event_type:
            return True

    return False


def find_resolved_filter_for_event(event, resolved_filters):
    """为事件查找已解析的过滤器"""
    event = event if isinstance(event, dict) else {}

    event_table = normalize_match_text(event.get("table"))
    event_field = normalize_match_text(event.get("field"))
    event_business_value = normalize_match_text(event.get("business_value"))
    if not event_business_value:
        event_business_value = normalize_match_text(event.get("value"))

    candidates = []

    # 第一优先级：source_event
    for item in resolved_filters:
        if not isinstance(item, dict):
            continue
        source_event = item.get("source_event")
        if source_event_matches(source_event, event):
            candidates.append(item)

    if candidates:
        return choose_unique_resolved_candidate(candidates)

    # 第二优先级：table + field + business value
    for item in resolved_filters:
        if not isinstance(item, dict):
            continue
        item_table = normalize_match_text(item.get("table"))
        item_field = normalize_match_text(item.get("field"))
        normalized = normalize_resolved_value(item)
        item_business_value = normalize_match_text(normalized.get("business_value"))

        if (item_table == event_table and item_field == event_field
                and item_business_value and item_business_value == event_business_value):
            candidates.append(item)

    if candidates:
        return choose_unique_resolved_candidate(candidates)

    # 第三优先级：table + field + business_field
    for item in resolved_filters:
        if not isinstance(item, dict):
            continue
        item_table = normalize_match_text(item.get("table"))
        item_field = normalize_match_text(item.get("field"))
        item_business_field = normalize_match_text(item.get("business_field"))

        if (item_table == event_table and item_field == event_field
                and item_business_field == event_business_value):
            candidates.append(item)

    if candidates:
        return choose_unique_resolved_candidate(candidates)

    return None


def choose_unique_resolved_candidate(candidates):
    """选择唯一的已解析候选"""
    normalized_candidates = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        normalized = normalize_resolved_value(item)
        normalized_candidates.append({
            "item": item,
            "business_value": normalized["business_value"],
            "physical_value": normalized["physical_value"],
            "physical_value_resolved": normalized["physical_value_resolved"]
        })

    resolved = [x for x in normalized_candidates if x["physical_value_resolved"]]
    if not resolved:
        return None

    physical_values = []
    for item in resolved:
        value = normalize_match_text(item["physical_value"])
        if value and value not in physical_values:
            physical_values.append(value)

    if len(physical_values) != 1:
        return None

    return resolved[0]["item"]


# ============================================================
# Relationship Graph
# ============================================================

def relationship_key(rel):
    """生成关系键"""
    if not isinstance(rel, dict):
        return ""
    return (clean_text(rel.get("source_table")) + "."
            + clean_text(rel.get("source_field")) + "->"
            + clean_text(rel.get("target_table")) + "."
            + clean_text(rel.get("target_field")))


def build_relationship_graph(schema):
    """构建关系图"""
    graph = {}
    relationships = schema.get("relationships", [])

    if not isinstance(relationships, list):
        return graph

    for rel in relationships:
        if not isinstance(rel, dict):
            continue

        source_table = clean_text(rel.get("source_table"))
        source_field = clean_text(rel.get("source_field"))
        target_table = clean_text(rel.get("target_table"))
        target_field = clean_text(rel.get("target_field"))

        if not all([source_table, source_field, target_table, target_field]):
            continue

        graph.setdefault(source_table, []).append(rel)

        reverse = dict(rel)
        reverse["source_table"] = target_table
        reverse["source_field"] = target_field
        reverse["target_table"] = source_table
        reverse["target_field"] = source_field

        graph.setdefault(target_table, []).append(reverse)

    return graph


def find_relationship_path(schema, start_table, target_table):
    """查找关系路径"""
    start_table = clean_text(start_table)
    target_table = clean_text(target_table)

    if not start_table or not target_table:
        return []

    if start_table == target_table:
        return []

    graph = build_relationship_graph(schema)
    queue = [(start_table, [])]
    visited = {start_table}

    while queue:
        current_table, path = queue.pop(0)

        for rel in graph.get(current_table, []):
            next_table = clean_text(rel.get("target_table"))
            if not next_table:
                continue

            next_path = path + [rel]
            if next_table == target_table:
                return next_path

            if next_table not in visited:
                visited.add(next_table)
                queue.append((next_table, next_path))

    return []


# ============================================================
# Required Tables 收集
# ============================================================

def collect_required_tables(main_table, entity, metrics, dimensions, filters, events, time):
    """收集需要的表"""
    tables = []

    def add_table(table):
        table = clean_text(table)
        if table and table not in tables:
            tables.append(table)

    add_table(main_table)

    if isinstance(entity, dict):
        add_table(entity.get("table"))

    for item in metrics:
        add_table(item.get("table"))

    for item in dimensions:
        add_table(item.get("table"))

    for item in filters:
        add_table(item.get("table"))

    for item in events:
        add_table(item.get("table"))

    if isinstance(time, dict):
        add_table(time.get("table"))

    return tables


# ============================================================
# Required Relationships 构建
# ============================================================

def build_required_relationships(schema, required_tables):
    """构建所需关系"""
    required_tables = [clean_text(x) for x in required_tables if clean_text(x)]

    if len(required_tables) <= 1:
        return {
            "relationships": [],
            "missing_relationships": []
        }

    relationships = []
    missing = []
    anchor = required_tables[0]

    for target in required_tables[1:]:
        path = find_relationship_path(schema, anchor, target)

        if not path:
            missing.append({
                "source_table": anchor,
                "target_table": target
            })
            continue

        for rel in path:
            key = relationship_key(rel)
            if not any(relationship_key(x) == key for x in relationships):
                relationships.append(rel)

    return {
        "relationships": relationships,
        "missing_relationships": missing
    }


# ============================================================
# Tables 构建
# ============================================================

def build_tables(required_tables, main_table, dimensions, metrics, filters, time):
    """构建表信息"""
    result = {}

    for table in required_tables:
        reasons = []
        roles = []

        if table == main_table:
            reasons.append("MAIN_RESULT_SOURCE")
            roles.append("MAIN")

        for dimension in dimensions:
            if dimension.get("table") == table:
                reason = "DIMENSION:" + clean_text(dimension.get("concept"))
                if reason not in reasons:
                    reasons.append(reason)
                if "DIMENSION_SOURCE" not in roles:
                    roles.append("DIMENSION_SOURCE")

        for metric in metrics:
            if metric.get("table") == table:
                reason = "METRIC:" + clean_text(metric.get("concept"))
                if reason not in reasons:
                    reasons.append(reason)
                if "METRIC_SOURCE" not in roles:
                    roles.append("METRIC_SOURCE")

        for item in filters:
            if item.get("table") == table:
                if "FILTER_SOURCE" not in roles:
                    roles.append("FILTER_SOURCE")

        if isinstance(time, dict) and time.get("table") == table:
            if "TIME_SOURCE" not in roles:
                roles.append("TIME_SOURCE")

        result[table] = {
            "reasons": reasons,
            "role": roles
        }

    return result


# ============================================================
# Query Shape 构建
# ============================================================

def build_query_shape(main_table, metrics, dimensions, events, required_tables, ranking):
    """构建查询形状"""
    has_ranking = bool(ranking.get("type") or ranking.get("direction"))
    group_by_required = len(dimensions) > 0
    event_strategy = "NONE"

    if events:
        event_strategy = "FILTER"

    requires_join = len(required_tables) > 1

    if group_by_required:
        result_type = "GROUPED_AGGREGATE"
    elif metrics:
        result_type = "AGGREGATE"
    else:
        result_type = "DETAIL"

    return {
        "event_strategy": event_strategy,
        "group_by_required": group_by_required,
        "has_ranking": has_ranking,
        "main_table": main_table,
        "requires_join": requires_join,
        "result_type": result_type
    }


# ============================================================
# Limit 构建
# ============================================================

def build_limit(query_state, ranking=None):
    """构建 Limit
    
    优先使用 ranking.limit（如果存在），否则使用 query_state.limit
    """
    state = as_dict(query_state)
    
    # 优先从 ranking 获取 limit
    if ranking and isinstance(ranking, dict):
        # 直接从 ranking 获取 limit
        ranking_limit = ranking.get("limit")
        if isinstance(ranking_limit, int) and ranking_limit > 0:
            return ranking_limit
        
        # 从嵌套的 ranking.value 获取 limit
        ranking_value = ranking.get("value", {})
        if isinstance(ranking_value, dict):
            ranking_limit = ranking_value.get("limit")
            if isinstance(ranking_limit, int) and ranking_limit > 0:
                return ranking_limit
    
    # 其次从 query_state 获取 limit
    limit = state.get("limit")
    if isinstance(limit, int) and limit > 0:
        return min(limit, 100)

    return 10


# ============================================================
# Filter Validation
# ============================================================

def validate_filters(filters):
    """验证过滤器"""
    violations = []

    for item in filters:
        table = clean_text(item.get("table"))
        field = clean_text(item.get("field"))
        physical_required = (
            item.get("physical_value") is not None
            or item.get("business_value") is not None
        )

        if not table:
            violations.append({
                "type": "FILTER_TABLE_MISSING",
                "table": "",
                "field": field,
                "message": "过滤条件缺少 table"
            })

        if not field:
            violations.append({
                "type": "FILTER_FIELD_MISSING",
                "table": table,
                "field": "",
                "message": "过滤条件缺少 field"
            })

        if physical_required:
            if not item.get("physical_value_resolved", False):
                violations.append({
                    "type": "FILTER_PHYSICAL_VALUE_MISSING",
                    "table": table,
                    "field": field,
                    "message": "过滤条件缺少已解析的 physical_value"
                })

    return violations


# ============================================================
# Event Validation
# ============================================================

def validate_events(events):
    """验证事件"""
    violations = []

    if not isinstance(events, list):
        return violations

    for event in events:
        if not isinstance(event, dict):
            continue

        event_type = clean_text(event.get("event_type")).upper()
        if event_type != "STATUS_EVENT":
            continue

        table = clean_text(event.get("table"))
        field = clean_text(event.get("field"))
        physical_value = event.get("physical_value")
        resolved = event.get("physical_value_resolved", False)

        if not resolved:
            violations.append({
                "type": "EVENT_VALUE_UNRESOLVED",
                "table": table,
                "field": field,
                "message": "STATUS_EVENT 缺少已解析的 physical_value"
            })

        if physical_value is None or clean_text(physical_value) == "":
            violations.append({
                "type": "EVENT_VALUE_MISSING",
                "table": table,
                "field": field,
                "message": "STATUS_EVENT 缺少明确 physical_value"
            })

    return violations


# ============================================================
# Query Plan Validation
# ============================================================

def validate_query_plan(query_plan, schema):
    """验证查询计划"""
    violations = []

    main_table = clean_text(query_plan.get("main_table"))

    if not main_table:
        violations.append({
            "type": "MAIN_TABLE_MISSING",
            "message": "Query Plan 缺少 main_table"
        })
    elif not table_exists(schema, main_table):
        violations.append({
            "type": "MAIN_TABLE_NOT_AVAILABLE",
            "table": main_table,
            "message": "main_table 不存在于 Schema Context"
        })

    required_tables = query_plan.get("required_tables", [])
    if not isinstance(required_tables, list):
        violations.append({
            "type": "REQUIRED_TABLES_INVALID",
            "message": "required_tables 格式非法"
        })
        required_tables = []

    for table in required_tables:
        if not table_exists(schema, table):
            violations.append({
                "type": "TABLE_NOT_AVAILABLE",
                "table": table,
                "message": "Query Plan 使用了 Schema Context 之外的表"
            })

    # Dimensions
    for dimension in query_plan.get("dimensions", []):
        table = clean_text(dimension.get("table"))
        field = clean_text(dimension.get("field"))
        if table and field and not field_exists(schema, table, field):
            violations.append({
                "type": "DIMENSION_FIELD_NOT_AVAILABLE",
                "table": table,
                "field": field,
                "message": "Dimension field 不存在于 Schema Context"
            })

    # Metrics
    for metric in query_plan.get("metrics", []):
        table = clean_text(metric.get("table"))
        field = clean_text(metric.get("field"))
        if table and field and not field_exists(schema, table, field):
            violations.append({
                "type": "METRIC_FIELD_NOT_AVAILABLE",
                "table": table,
                "field": field,
                "message": "Metric field 不存在于 Schema Context"
            })

    # Filters
    filter_violations = validate_filters(query_plan.get("filters", []))
    violations.extend(filter_violations)

    # Events
    event_violations = validate_events(query_plan.get("events", []))
    violations.extend(event_violations)

    # Missing relationships
    missing_relationships = query_plan.get("missing_relationships", [])
    if missing_relationships:
        violations.append({
            "type": "RELATIONSHIP_MISSING",
            "message": "required tables 之间不存在可用关系"
        })

    return violations


# ============================================================
# 格式化 SQL 所需的查询计划信息
# ============================================================

def format_sql_query_plan(query_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    格式化查询计划，生成 SQL 所需的表、JOIN、SELECT、WHERE、GROUP BY、ORDER BY、LIMIT 信息

    返回：
        tables: 需要的表列表
        joins: JOIN 信息列表
        select_fields: SELECT 字段列表
        where_conditions: WHERE 条件列表
        group_by: GROUP BY 字段列表
        order_by: ORDER BY 字段列表
        limit: LIMIT 值
    """
    tables = list(query_plan.get("tables", {}).keys())
    relationships = query_plan.get("relationships", [])
    metrics = query_plan.get("metrics", [])
    dimensions = query_plan.get("dimensions", [])
    filters = query_plan.get("filters", [])
    time_obj = query_plan.get("time")
    ranking = query_plan.get("ranking", {})
    main_table = query_plan.get("main_table", "")

    # 构建 JOIN 信息
    joins = []
    for rel in relationships:
        # 从关系定义中获取 JOIN 类型，默认为 INNER
        join_type = rel.get("type", "INNER").upper()
        # 标准化 JOIN 类型
        if join_type not in ["INNER", "LEFT", "RIGHT", "FULL", "CROSS"]:
            join_type = "INNER"
        joins.append({
            "type": join_type,
            "source_table": rel.get("source_table"),
            "source_field": rel.get("source_field"),
            "target_table": rel.get("target_table"),
            "target_field": rel.get("target_field")
        })

    # 构建 SELECT 字段
    select_fields = []

    # 添加维度字段
    for dim in dimensions:
        table = dim.get("table", "")
        field = dim.get("field", "")
        if table and field:
            select_fields.append({
                "table": table,
                "field": field,
                "alias": dim.get("concept", field),
                "type": "dimension"
            })

    # 添加度量字段
    for metric in metrics:
        table = metric.get("table", "")
        field = metric.get("field", "")
        agg = metric.get("aggregation", "SUM")
        if table and field:
            select_fields.append({
                "table": table,
                "field": field,
                "aggregation": agg,
                "alias": metric.get("concept", field),
                "type": "metric"
            })

    # 构建 WHERE 条件
    where_conditions = []

    # 检测 filters 中是否有时间字段，避免与 time_obj 的时间条件重复
    # 如果 time_obj 有时间值，跳过 filters 中相同字段的时间条件
    time_fields_to_skip = set()
    if time_obj:
        time_table = time_obj.get("table", "")
        time_field = time_obj.get("field", "")
        if time_table and time_field:
            time_fields_to_skip.add((time_table, time_field))

    # 添加过滤条件
    for f in filters:
        table = f.get("table", "")
        field = f.get("field", "")
        operator = f.get("operator", "=")
        physical_value = f.get("physical_value")

        # 跳过与 time_obj 重复的时间字段条件
        if (table, field) in time_fields_to_skip:
            continue

        if table and field and physical_value is not None:
            where_conditions.append({
                "table": table,
                "field": field,
                "operator": operator,
                "value": physical_value,
                "physical_value": physical_value,  # 与 prompt 规则一致，避免 LLM 混淆
                "type": "filter"
            })

    # 添加时间条件
    if time_obj:
        table = time_obj.get("table", "")
        field = time_obj.get("field", "")
        start = time_obj.get("start")
        end = time_obj.get("end")

        if table and field and start and end:
            where_conditions.append({
                "table": table,
                "field": field,
                "operator": ">=",
                "value": start,
                "type": "time_start"
            })
            where_conditions.append({
                "table": table,
                "field": field,
                "operator": "<",
                "value": end,
                "type": "time_end"
            })

    # 添加事件条件
    for event in query_plan.get("events", []):
        event_type = event.get("event_type", "")
        table = event.get("table", "")
        field = event.get("field", "")
        physical_value = event.get("physical_value")

        if event_type == "STATUS_EVENT" and table and field and physical_value is not None:
            where_conditions.append({
                "table": table,
                "field": field,
                "operator": "=",
                "value": physical_value,
                "type": "event"
            })

    # 构建 GROUP BY
    group_by = []
    for dim in dimensions:
        table = dim.get("table", "")
        field = dim.get("field", "")
        if table and field:
            group_by.append({
                "table": table,
                "field": field
            })

    # 构建 ORDER BY
    order_by = []
    
    # 处理 ranking 嵌套结构：ranking.value 包含 type, order, metric 等信息
    ranking_value_obj = ranking.get("value", {})
    if isinstance(ranking_value_obj, dict) and ranking_value_obj:
        ranking_type = ranking_value_obj.get("type", "")
        ranking_direction = ranking_value_obj.get("direction", "") or ranking_value_obj.get("order", "")
        metric_name = ranking_value_obj.get("metric", "")
    else:
        # 没有嵌套 value，直接从 ranking 顶层获取
        ranking_type = ranking.get("type", "")
        ranking_direction = ranking.get("direction", "") or ranking.get("order", "")
        metric_name = ranking.get("metric", "")

    if ranking_type and ranking_direction:
        # 根据 ranking 配置构建排序
        if ranking_type in ["metric", "dimension", "ranking"]:
            # 找到对应的字段
            target_list = metrics if ranking_type in ["metric", "ranking"] else dimensions
            # 优先使用 ranking.value.metric 或 ranking.metric
            target_metric = metric_name or ranking.get("metric", "")
            if target_metric:
                for item in target_list:
                    if item.get("concept") == target_metric or item.get("name") == target_metric:
                        # 如果有 GROUP BY 且排序的是聚合指标，使用聚合别名而不是原始列名
                        order_by_entry = {
                            "direction": ranking_direction.upper()
                        }
                        if group_by and item.get("aggregation"):
                            order_by_entry["alias"] = item.get("alias", item.get("concept", ""))
                            order_by_entry["use_alias"] = True
                        else:
                            order_by_entry["table"] = item.get("table", "")
                            order_by_entry["field"] = item.get("field", "")
                            order_by_entry["use_alias"] = False
                        order_by.append(order_by_entry)
                        break

    # Limit
    limit = query_plan.get("limit", 10)

    return {
        "tables": tables,
        "joins": joins,
        "select_fields": select_fields,
        "where_conditions": where_conditions,
        "group_by": group_by,
        "order_by": order_by,
        "limit": limit,
        "main_table": main_table
    }


# ============================================================
# 节点创建函数
# ============================================================

def create_query_plan_builder_node():
    """创建查询计划构建器节点"""

    def query_plan_builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== QUERY PLAN BUILDER NODE INPUT ==========")
        print(f"query_state: {state.get('query_state')}")
        print(f"semantic_result: {state.get('semantic_result')}")

        query_state = state.get("query_state", {})
        semantic_result = state.get("semantic_result", {})
        resolved_filters = state.get("resolved_filters", [])
        print(f"[DEBUG] resolved_filters from state: {resolved_filters}")
        schema_context = state.get("schema_context", {})

        try:
            # Parse
            state_parsed = as_dict(query_state)
            semantic = as_dict(semantic_result)
            schema = normalize_schema_context(schema_context)

            # Main Table
            main_table = infer_main_table(semantic, state_parsed, schema)

            # Entity
            entity = build_entity(semantic)

            # Metrics
            metrics = build_metrics(semantic)

            # Dimensions
            dimensions = build_dimensions(semantic)

            # Group By
            group_by = build_group_by(dimensions)

            # Filters - 优先使用 filter_value_resolver 节点的输出（包含字段纠错）
            # filter_value_resolver 运行在 query_plan_builder 之前，已将 business_value 解析为 physical_value
            fvr_resolved = state.get("resolved_filters", [])
            fvr_unresolved = state.get("unresolved_filters", [])
            raw_filters = semantic.get("filters", [])
            if fvr_resolved or fvr_unresolved:
                # filter_value_resolver 已运行，合并其输出（resolved 优先）
                all_fvr_filters = fvr_resolved + fvr_unresolved
                filters = build_filters(all_fvr_filters)
                print(f"[DEBUG] 使用 filter_value_resolver 输出: resolved={len(fvr_resolved)}, unresolved={len(fvr_unresolved)}")
            elif raw_filters:
                # filter_value_resolver 未运行，fallback 到本地解析
                filters = build_filters(resolve_filter_values(raw_filters))
            else:
                filters = []

            # Time - 传入 query_state 以获取 time 信息
            time_obj = build_time(semantic, query_state=state_parsed, metadata=schema_context.get("metadata"))
            print(f"[DEBUG] query_plan_builder time_obj: {time_obj}")

            # Events
            events = build_events(semantic, schema_context, resolved_filters)

            # Ranking
            ranking = build_ranking(semantic)

            # Comparison
            comparison = build_comparison(semantic)

            # Required Tables
            required_tables = collect_required_tables(
                main_table, entity, metrics, dimensions,
                filters, events, time_obj
            )

            # Relationships
            relationship_result = build_required_relationships(schema, required_tables)
            relationships = relationship_result["relationships"]
            missing_relationships = relationship_result["missing_relationships"]

            # Tables
            tables = build_tables(
                required_tables, main_table, dimensions,
                metrics, filters, time_obj
            )

            # Query Shape
            query_shape = build_query_shape(
                main_table, metrics, dimensions, events,
                required_tables, ranking
            )

            # Limit
            limit = build_limit(state_parsed, ranking)

            # Query State Version
            query_state_version = state_parsed.get("version")

            # 构建查询计划
            query_plan = {
                "comparison": comparison,
                "dimensions": dimensions,
                "entity": entity,
                "events": events,
                "filters": filters,
                "group_by": group_by,
                "limit": limit,
                "main_table": main_table,
                "metrics": metrics,
                "missing_relationships": missing_relationships,
                "query_shape": query_shape,
                "query_state_version": query_state_version,
                "ranking": ranking,
                "relationships": relationships,
                "required_tables": required_tables,
                "status": "READY",
                "tables": tables,
                "time": time_obj,
                "version": 5
            }

            # 最终验证
            violations = validate_query_plan(query_plan, schema)

            # BLOCKED
            if violations:
                query_plan["status"] = "BLOCKED"
                return {
                    "status": "BLOCKED",
                    "query_plan": query_plan,
                    "error_message": json.dumps(violations, ensure_ascii=False)
                }

            # READY
            elapsed = time.time() - start_time
            print(f"========== QUERY PLAN BUILDER NODE OUTPUT ==========")
            print(f"query_plan status: {query_plan.get('status')}")
            print(f"[TIMER] Query Plan Builder: {elapsed:.2f}s")
            print(f"=====================================================\n")

            return {
                "status": "READY",
                "query_plan": query_plan,
                "error_message": "",
                "node_timings": {"query_plan_builder": elapsed}
            }

        except Exception as e:
            return {
                "status": "BLOCKED",
                "query_plan": {
                    "status": "BLOCKED",
                    "version": 5
                },
                "error_message": "Query Plan Builder 执行异常: " + str(e)
            }

    return query_plan_builder_node


def create_query_plan_formatter_node():
    """创建查询计划格式化节点"""

    def query_plan_formatter_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== QUERY PLAN FORMATTER NODE INPUT ==========")

        query_plan = state.get("query_plan", {})

        if not query_plan:
            return {
                "sql_query_plan": {},
                "node_timings": {"query_plan_formatter": 0}
            }

        # 格式化 SQL 查询计划
        sql_query_plan = format_sql_query_plan(query_plan)

        # 传递嵌套查询配置（semantic_result.extensions.sub_query）到 SQL 编译器
        # Query Plan 是 SQL Generator 唯一的结构来源，sub_query 必须进入查询计划
        semantic_result = state.get("semantic_result", {}) or {}
        sub_query = (semantic_result.get("extensions", {}) or {}).get("sub_query")
        if sub_query and sub_query.get("field"):
            sql_query_plan["sub_query"] = sub_query
            print(f"[DEBUG] sql_query_plan 注入 sub_query: {sub_query}")

        elapsed = time.time() - start_time
        print(f"========== QUERY PLAN FORMATTER NODE OUTPUT ==========")
        print(f"sql_query_plan: {json.dumps(sql_query_plan, ensure_ascii=False)}")
        print(f"[TIMER] Query Plan Formatter: {elapsed:.2f}s")
        print(f"======================================================\n")

        return {
            "sql_query_plan": sql_query_plan,
            "query_plan": sql_query_plan,  # Also add as query_plan for compatibility
            "node_timings": {"query_plan_formatter": elapsed}
        }

    return query_plan_formatter_node
