"""
Filter Value Resolver 节点
用于将 filters 中的 business_value 解析为 physical_value
"""

import json
import time
from typing import Dict, Any, List

import pymysql
import os


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


def query_dimension_values(business_values: List[str], dimension_code: str = None) -> List[Dict]:
    """查询 semantic_dimension_values 表"""
    if not business_values:
        return []

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(business_values))
            sql = f"""
                SELECT dimension_id, dimension_name,
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
    """查询 semantic_value_aliases 表（通过 JOIN 获取 physical_value 和 table/field）"""
    if not business_values:
        return []

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(business_values))
            # 通过 JOIN semantic_dimension_values 获取 physical_value 和 table/field
            sql = f"""
                SELECT a.alias, dv.physical_value, dv.value_name as target_value_name, 
                       dv.dimension_id, dim.table_name, dim.field_name
                FROM semantic_value_aliases a
                JOIN semantic_dimension_values dv ON a.value_id = dv.id
                JOIN semantic_dimensions dim ON dv.dimension_id = dim.id
                WHERE a.alias IN ({placeholders})
            """

            cursor.execute(sql, business_values)
            result = cursor.fetchall()
            conn.close()

            return [dict(row) for row in result] if result else []

    except Exception as e:
        print(f"[ERROR] query_value_aliases: {str(e)}")
        return []


def query_user_ids_by_names(names: List[str]) -> Dict[str, str]:
    """人名/用户名 → user_id 解析（用于 sales_id 等用户引用字段）

    支持"李四的销售额"这类他人引用：LLM 可能输出 value='李四'，
    需要查询 users 表把人名解析为物理 user_id。

    返回: {name_or_username: str(user_id)}
    """
    if not names:
        return {}
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(names))
            sql = f"""
                SELECT id, username, name
                FROM users
                WHERE name IN ({placeholders}) OR username IN ({placeholders})
            """
            cursor.execute(sql, (*names, *names))
            rows = cursor.fetchall()
        conn.close()

        mapping = {}
        for r in rows:
            uid = str(r.get("id"))
            if r.get("name"):
                mapping[r["name"]] = uid
            if r.get("username"):
                mapping[r["username"]] = uid
        return mapping
    except Exception as e:
        print(f"[ERROR] query_user_ids_by_names: {str(e)}")
        return {}


def query_customer_ids_by_names(names: List[str]) -> Dict[str, str]:
    """公司名/客户名 → customer_id 解析（用于 customer_id 等客户引用字段）

    多轮对话场景："它今年的利润是多少？"改写后 filter 可能是
    customer_id = '北京云计算有限公司'（业务名），需要查询 customers 表
    把公司名解析为物理 customer_id，否则下游会把 filter 错误纠成
    orders.name LIKE（orders 表没有 name 列，触发 UNKNOWN_FIELD）。

    仅精确匹配：调用方需区分"真实公司名"（能解析）和"泛化词/字段名等垃圾值"
    （解析不到，由调用方决定跳过或走 LIKE 纠错路径）。

    返回: {name: str(customer_id)}
    """
    if not names:
        return {}
    try:
        conn = get_db_connection()
        mapping = {}
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(names))
            cursor.execute(
                f"SELECT id, name FROM customers WHERE name IN ({placeholders})",
                names
            )
            for r in cursor.fetchall():
                if r.get("name") and r.get("id") is not None:
                    mapping[r["name"]] = str(r["id"])
        conn.close()
        return mapping
    except Exception as e:
        print(f"[ERROR] query_customer_ids_by_names: {str(e)}")
        return {}


def create_filter_value_resolver_node():
    """创建 Filter Value Resolver 节点"""

    def filter_value_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 filters 中的 business_value → physical_value

        输入:
            - semantic_result: 语义解析结果，包含 filters
            - query_state: 查询状态，包含 filters

        输出:
            - resolved_filters: 解析后的 filters 列表
            - unresolved_filters: 未解析的 filters 列表
        """
        start_time = time.time()

        print("\n========== FILTER VALUE RESOLVER NODE INPUT ==========")
        print(f"semantic_result: {state.get('semantic_result', {})}")
        print(f"query_state: {state.get('query_state', {})}")
        print("=====================================================\n")

        # 优先从 semantic_result 获取 filters，其次从 query_state 获取
        semantic_result = state.get("semantic_result", {})
        query_state = state.get("query_state", {})

        # semantic_result 中的 filters
        semantic_filters = semantic_result.get("filters", []) if isinstance(semantic_result, dict) else []
        # query_state 中的 filters
        query_filters = query_state.get("filters", []) if isinstance(query_state, dict) else []

        # 优先使用 semantic_result.filters，否则使用 query_state.filters
        filters = semantic_filters if semantic_filters else query_filters

        # 收集所有需要解析的业务值
        business_values_to_resolve = []
        filter_value_map = {}  # business_value -> filter index

        for idx, f in enumerate(filters):
            value = f.get("value", "")
            if not value or value == "":
                continue

            # 跳过已经是物理值的（如日期、数字）
            if value.isdigit() or "-" in value or "/" in value:
                continue

            # 检查是否需要解析
            if value not in filter_value_map:
                business_values_to_resolve.append(value)
                filter_value_map[value] = []

            filter_value_map[value].append(idx)

        print(f"[DEBUG] Business values to resolve: {business_values_to_resolve}")

        # 查询数据库获取物理值
        dimension_values = query_dimension_values(business_values_to_resolve)
        aliases = query_value_aliases(business_values_to_resolve)

        # 构建 business_value -> 完整解析信息的映射
        value_mapping = {}  # business_value -> {physical_value, table, field}

        # 从 dimension_values 中获取
        for dv in dimension_values:
            value_name = dv.get("value_name", "")
            physical_value = dv.get("physical_value", "")
            dimension_id = dv.get("dimension_id")
            if value_name and physical_value:
                if value_name not in value_mapping:
                    value_mapping[value_name] = {
                        "physical_value": physical_value,
                        "dimension_id": dimension_id,
                        "table": dv.get("table_name", ""),
                        "field": dv.get("field_name", "")
                    }

        # 从 aliases 中获取（aliases 包含更完整的 table/field 信息）
        for alias in aliases:
            alias_name = alias.get("alias", "")
            physical_value = alias.get("physical_value", "")
            if alias_name and physical_value:
                # aliases 的 table/field 信息更准确，优先使用
                value_mapping[alias_name] = {
                    "physical_value": physical_value,
                    "dimension_id": alias.get("dimension_id"),
                    "table": alias.get("table_name", ""),
                    "field": alias.get("field_name", "")
                }

        print(f"[DEBUG] Value mapping: {value_mapping}")

        # ========== 用户引用字段的人名 → user_id 解析 ==========
        # 支持"李四的销售额"这类他人引用：value 是人名时查 users 表解析为物理 user_id
        schema = state.get("schema", {}) or {}
        user_ref_fields = schema.get("user_reference_fields") or {}
        owner_field_names = {
            "sales_id", "owner_id", "creator_id", "assignee_id", "approver_id",
            "agent_id", "created_by", "manager_id",
        }
        for ref in (user_ref_fields.values() if isinstance(user_ref_fields, dict) else []):
            if isinstance(ref, dict) and ref.get("type", "owner") in ("owner", "creator", "approver", "assignee"):
                owner_field_names.add(ref.get("field"))

        person_names = set()
        for f in filters:
            v = str(f.get("value", "") or "")
            if (f.get("field") in owner_field_names and v
                    and not v.isdigit() and not v.startswith("${")
                    and "-" not in v and "/" not in v):
                person_names.add(v)
        user_name_map = query_user_ids_by_names(list(person_names)) if person_names else {}
        if user_name_map:
            print(f"[DEBUG] User name mapping: {user_name_map}")

        # ========== 公司/客户名的公司名 → customer_id 解析 ==========
        # 多轮对话场景："它今年的利润是多少？"改写后 filter 是 customer_id = '北京云计算有限公司'（业务名），
        # 需查 customers 表解析为物理 id，否则 unresolved 后下游字段纠错会生成 orders.name LIKE（orders 无 name 列）
        _company_concept_words = ("公司", "客户", "公司名", "客户名", "公司名称", "客户名称")
        company_names = set()
        for f in filters:
            v = str(f.get("value", "") or "")
            if f.get("field") in ("customer_id", "id") and v and not v.isdigit() and v not in _company_concept_words:
                company_names.add(v)
        customer_name_map = query_customer_ids_by_names(list(company_names)) if company_names else {}
        if customer_name_map:
            print(f"[DEBUG] Customer name mapping: {customer_name_map}")

        # 解析 filters
        resolved_filters = []
        unresolved_filters = []

        for idx, f in enumerate(filters):
            value = f.get("value", "")
            resolved_f = f.copy()

            # 用户引用字段：人名/用户名 → user_id（优先级高于 dimension 映射）
            if f.get("field") in owner_field_names and value in user_name_map:
                uid = user_name_map[value]
                resolved_f["physical_value"] = uid
                resolved_f["value"] = uid
                resolved_f["physical_value_resolved"] = True
                # 就地同步回 state 容器（semantic_result.filters / query_state.filters 是同一批对象）
                f["physical_value"] = uid
                f["value"] = uid
                resolved_filters.append(resolved_f)
                print(f"[DEBUG] Resolved user filter: {value} -> {uid}, field={f.get('field')}")
                continue

            # 公司/客户引用字段：公司名 → customer_id（优先级高于 dimension 映射）
            if f.get("field") in ("customer_id", "id") and value in customer_name_map:
                cid = customer_name_map[value]
                resolved_f["physical_value"] = cid
                resolved_f["value"] = cid
                resolved_f["physical_value_resolved"] = True
                # 就地同步回 state 容器（semantic_result.filters / query_state.filters 是同一批对象）
                f["physical_value"] = cid
                f["value"] = cid
                resolved_filters.append(resolved_f)
                print(f"[DEBUG] Resolved customer filter: {value} -> {cid}, field={f.get('field')}")
                continue

            # 如果可以解析
            if value in value_mapping:
                mapping = value_mapping[value]
                resolved_f["physical_value"] = mapping["physical_value"]
                resolved_f["physical_value_resolved"] = True

                # 如果 filter 没有 table/field，从映射中获取
                if not resolved_f.get("table"):
                    resolved_f["table"] = mapping.get("table", "")
                if not resolved_f.get("field"):
                    resolved_f["field"] = mapping.get("field", "")

                resolved_filters.append(resolved_f)
                print(f"[DEBUG] Resolved filter: {value} -> {mapping['physical_value']}, table={resolved_f.get('table')}, field={resolved_f.get('field')}")
            else:
                # 保留原值作为 fallback
                resolved_f["physical_value"] = value
                resolved_f["physical_value_resolved"] = False
                unresolved_filters.append(resolved_f)
                print(f"[DEBUG] Could not resolve filter: {value}")

        # 特殊字段名纠错：LLM 偶发把实体名 filter 的 field 映射错（如 company_name 写成 customer_id）
        # 行 44 曾出现：field='customer_id', value='杭州科技有限公司' → 应该是 field='name', value='%杭州科技有限公司%'
        field_corrections = {
            "customer_id": "name",  # 实体名 filter 不应该用 customer_id
            "id": "name",
        }

        # resolved_filters 纠错
        for f in resolved_filters:
            ffield = f.get("field", "")
            fvalue = str(f.get("physical_value", ""))
            if ffield in field_corrections and not fvalue.replace("%", "").isdigit():
                corrected = field_corrections[ffield]
                f["field"] = corrected
                if not fvalue.startswith("%") and not fvalue.endswith("%"):
                    f["physical_value"] = f"%{fvalue}%"
                    f["operator"] = "LIKE"
                print(f"[DEBUG] resolved 字段纠错: {ffield} -> {corrected}, value -> {f['physical_value']}")

        # unresolved_filters 纠错
        for f in unresolved_filters:
            ffield = f.get("field", "")
            fvalue = str(f.get("value", ""))
            if ffield in field_corrections and not fvalue.isdigit():
                # 非数字的实体名用 id/customer_id 作为 field 是错误的
                corrected = field_corrections[ffield]
                f["field"] = corrected
                # name 列属于 customers 表（orders 没有 name 列，否则触发 UNKNOWN_FIELD）
                f["table"] = "customers"
                # 同时修正 physical_value：加通配符以便 LIKE 匹配
                if not fvalue.startswith("%") and not fvalue.endswith("%"):
                    f["physical_value"] = f"%{fvalue}%"
                    f["operator"] = "LIKE"
                print(f"[DEBUG] 字段纠错: {ffield} -> {corrected}, value -> {f['physical_value']}")

        elapsed = time.time() - start_time

        print("\n========== FILTER VALUE RESOLVER NODE OUTPUT ==========")
        print(f"resolved_filters count: {len(resolved_filters)}")
        print(f"unresolved_filters count: {len(unresolved_filters)}")
        print(f"elapsed: {elapsed:.2f}s")
        print("=====================================================\n")

        return {
            "resolved_filters": resolved_filters,
            "unresolved_filters": unresolved_filters,
            "node_timings": {"filter_value_resolver": elapsed}
        }

    return filter_value_resolver_node
