"""
值语义查询和解析节点
"""

import json
import time
import os
from typing import Dict, Any, List, Optional

import pymysql


def get_db_connection():
    """获取数据库连接"""
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "63888"))
    db_name = os.getenv("DB_NAME", "metadata")

    return pymysql.connect(
        host=db_host,
        port=db_port,
        user="root",
        password=db_password,
        database=db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )


def query_dimension_values(business_values: List[str], dimension_code: Optional[str] = None) -> List[Dict]:
    """
    查询 semantic_dimension_values 表

    Args:
        business_values: 业务值列表
        dimension_code: 维度编码（可选）

    Returns:
        匹配的物理值列表
    """
    if not business_values:
        return []

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 构建查询条件
            placeholders = ", ".join(["%s"] * len(business_values))
            sql = f"""
                SELECT id, dimension_id, dimension_code, dimension_name,
                       value_name, value_code, physical_value, value_type
                FROM semantic_dimension_values
                WHERE value_name IN ({placeholders})
            """

            params = business_values
            if dimension_code:
                sql += " AND dimension_code = %s"
                params.append(dimension_code)

            cursor.execute(sql, params)
            result = cursor.fetchall()
            conn.close()

            return [dict(row) for row in result] if result else []

    except Exception as e:
        print(f"[ERROR] query_dimension_values: {str(e)}")
        return []


def query_value_aliases(business_values: List[str]) -> List[Dict]:
    """
    查询 semantic_value_aliases 表

    Args:
        business_values: 业务值列表

    Returns:
        匹配的别名映射列表
    """
    if not business_values:
        return []

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(business_values))
            sql = f"""
                SELECT id, alias, dimension_id, dimension_code, dimension_name,
                       target_value_name, target_value_code, physical_value
                FROM semantic_value_aliases
                WHERE alias IN ({placeholders})
            """

            cursor.execute(sql, business_values)
            result = cursor.fetchall()
            conn.close()

            return [dict(row) for row in result] if result else []

    except Exception as e:
        print(f"[ERROR] query_value_aliases: {str(e)}")
        return []


def create_value_lookup_prep_node():
    """值查询准备节点 - 从 semantic_result 中提取需要查询的业务值"""

    def value_lookup_prep_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== VALUE LOOKUP PREP NODE INPUT ==========")

        semantic_result = state.get("semantic_result", {})
        query_state = state.get("query_state", {})

        # 提取需要查询的业务值
        lookup_items = []

        # 从 semantic_result 中提取需要解析的业务值
        semantic_mapping = semantic_result.get("semantic_mapping", {})

        # 提取维度过滤条件中的业务值
        filters = query_state.get("filters", [])
        for f in filters:
            field = f.get("field", "")
            operator = f.get("operator", "")
            value = f.get("value")

            # 跳过空值
            if value is None or value == "":
                continue

            # 收集业务值
            if isinstance(value, str):
                business_values = [value]
            elif isinstance(value, list):
                business_values = value
            else:
                business_values = [str(value)]

            for bv in business_values:
                # 检查是否需要语义解析（非物理值）
                # 例如："华东" 需要解析为物理值，"2024-01-01" 不需要
                if bv and not bv.isdigit() and "-" not in bv and "/" not in bv:
                    lookup_items.append({
                        "business_value": bv,
                        "field": field,
                        "operator": operator,
                        "source": "filter"
                    })

        # 去重
        seen = set()
        unique_lookup_items = []
        for item in lookup_items:
            key = item["business_value"]
            if key not in seen:
                seen.add(key)
                unique_lookup_items.append(item)

        elapsed = time.time() - start_time

        print(f"lookup_items: {unique_lookup_items}")
        print(f"[TIMER] Value Lookup Prep: {elapsed:.2f}s")
        print(f"================================================\n")

        return {
            "lookup_items": unique_lookup_items,
            "node_timings": {"value_lookup_prep": elapsed}
        }

    return value_lookup_prep_node


def create_value_semantic_lookup_node():
    """值语义查询节点 - 根据用户输入的值，查询对应的数据库记录"""

    def value_semantic_lookup_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== VALUE SEMANTIC LOOKUP NODE INPUT ==========")

        lookup_items = state.get("lookup_items", [])
        metadata = state.get("metadata", {})

        # 存储查询结果
        lookup_results = []

        if not lookup_items:
            print("No lookup items to query")
            return {
                "lookup_results": [],
                "node_timings": {"value_semantic_lookup": time.time() - start_time}
            }

        # 收集所有业务值
        business_values = [item["business_value"] for item in lookup_items]

        print(f"Querying for business values: {business_values}")

        # 1. 查询 semantic_dimension_values 表
        dimension_values = query_dimension_values(business_values)

        # 2. 查询 semantic_value_aliases 表
        aliases = query_value_aliases(business_values)

        # 3. 从 metadata 中获取已加载的维度值
        metadata_dimension_values = metadata.get("semantic_dimension_values", [])
        metadata_aliases = metadata.get("semantic_value_aliases", [])

        # 合并所有来源的结果
        all_dimension_values = dimension_values + metadata_dimension_values
        all_aliases = aliases + metadata_aliases

        # 构建查询结果
        for item in lookup_items:
            business_value = item["business_value"]
            field = item.get("field", "")
            operator = item.get("operator", "")

            # 优先从 dimension_values 匹配
            physical_value = None
            matched_source = None

            for dv in all_dimension_values:
                if dv.get("value_name") == business_value:
                    physical_value = dv.get("physical_value")
                    matched_source = "dimension_values"
                    break

            # 如果没匹配，尝试从 aliases 匹配
            if not physical_value:
                for alias in all_aliases:
                    if alias.get("alias") == business_value:
                        physical_value = alias.get("physical_value")
                        matched_source = "aliases"
                        break

            # 如果还没匹配，检查是否直接就是物理值
            if not physical_value:
                # 假设业务值就是物理值
                physical_value = business_value
                matched_source = "direct"

            lookup_results.append({
                "business_value": business_value,
                "physical_value": physical_value,
                "field": field,
                "operator": operator,
                "source": matched_source,
                "matched": matched_source in ["dimension_values", "aliases"]
            })

        elapsed = time.time() - start_time

        print(f"lookup_results: {json.dumps(lookup_results, ensure_ascii=False)}")
        print(f"[TIMER] Value Semantic Lookup: {elapsed:.2f}s")
        print(f"======================================================\n")

        return {
            "lookup_results": lookup_results,
            "node_timings": {"value_semantic_lookup": elapsed}
        }

    return value_semantic_lookup_node


def create_value_semantic_resolver_node():
    """值语义解析器节点 - 解析用户输入的业务值对应的物理值"""

    def value_semantic_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== VALUE SEMANTIC RESOLVER NODE INPUT ==========")

        lookup_results = state.get("lookup_results", [])
        semantic_result = state.get("semantic_result", {})
        query_state = state.get("query_state", {})

        # 解析结果
        resolved_values = []
        unresolved_values = []

        for item in lookup_results:
            business_value = item.get("business_value")
            physical_value = item.get("physical_value")
            matched = item.get("matched", False)

            if matched:
                resolved_values.append({
                    "business_value": business_value,
                    "physical_value": physical_value,
                    "status": "resolved"
                })
            else:
                unresolved_values.append({
                    "business_value": business_value,
                    "physical_value": physical_value,
                    "status": "unresolved"
                })

        # 更新 query_state 中的 filters，使用物理值
        updated_filters = []
        filters = query_state.get("filters", [])

        for f in filters:
            field = f.get("field", "")
            operator = f.get("operator", "")
            value = f.get("value")

            # 尝试找到对应的物理值
            new_value = value
            if isinstance(value, str):
                for item in lookup_results:
                    if item.get("business_value") == value and item.get("matched"):
                        new_value = item.get("physical_value")
                        break
            elif isinstance(value, list):
                new_value = []
                for v in value:
                    resolved_v = v
                    for item in lookup_results:
                        if item.get("business_value") == v and item.get("matched"):
                            resolved_v = item.get("physical_value")
                            break
                    new_value.append(resolved_v)

            updated_filters.append({
                "field": field,
                "operator": operator,
                "value": new_value
            })

        # 构建解析结果
        result = {
            "resolved": len(unresolved_values) == 0,
            "resolved_values": resolved_values,
            "unresolved_values": unresolved_values,
            "total": len(lookup_results),
            "resolved_count": len(resolved_values),
            "unresolved_count": len(unresolved_values)
        }

        elapsed = time.time() - start_time

        print(f"value_semantic_result: {json.dumps(result, ensure_ascii=False)}")
        print(f"updated_filters: {json.dumps(updated_filters, ensure_ascii=False)}")
        print(f"[TIMER] Value Semantic Resolver: {elapsed:.2f}s")
        print(f"=====================================================\n")

        return {
            "value_semantic_result": result,
            "query_state": {
                **query_state,
                "filters": updated_filters
            },
            "node_timings": {"value_semantic_resolver": elapsed}
        }

    return value_semantic_resolver_node
