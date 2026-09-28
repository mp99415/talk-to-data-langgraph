"""
验证器节点
"""

import re
import time
from typing import Dict, Any, List


def create_query_state_validator_node():
    """创建 QUERY STATE VALIDATOR 节点"""

    def validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== QUERY STATE VALIDATOR NODE INPUT ==========")
        print(f"query_state: {state.get('query_state', {})}")
        print(f"========================================================\n")

        query_state = state.get("query_state", {})
        errors = validate_query_state(query_state)

        elapsed = time.time() - start_time

        print(f"\n========== QUERY STATE VALIDATOR NODE OUTPUT ==========")
        print(f"validation_errors: {errors}")
        print(f"query_state_status: {'VALID' if not errors else 'INVALID'}")
        print(f"[TIMER] Query State Validator: {elapsed:.4f}s")
        print(f"========================================================\n")

        return {
            "validation_errors": errors,
            "query_state_status": "VALID" if not errors else "INVALID",
            "node_timings": {"query_state_validator": elapsed}
        }

    return validator_node


def validate_query_state(query_state: Dict[str, Any]) -> List[str]:
    """验证 Query State 的有效性"""
    errors = []
    
    if not query_state:
        errors.append("Query State 不能为空")
        return errors
    
    has_metrics = query_state.get("metrics")
    has_dimensions = query_state.get("dimensions")
    has_filters = query_state.get("filters")
    has_time = query_state.get("time")
    has_entity = query_state.get("entity")
    
    if not any([has_metrics, has_dimensions, has_filters, has_time, has_entity]):
        errors.append("Query State 缺少有效的查询条件（metrics/dimensions/filters/time/entity）")
    
    return errors


def create_sql_validator_node():
    """创建 SQL VALIDATOR 节点"""

    DANGEROUS_KEYWORDS = [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
        "TRUNCATE", "CREATE", "GRANT", "REVOKE"
    ]

    # SELECT 列提取（支持 `col`、`table.col`、`SUM(col)` 等）
    _SELECT_FIELD_RE = re.compile(
        r"`?(?P<field>[A-Za-z_][A-Za-z0-9_]*)`?",
        re.IGNORECASE,
    )
    _AGG_FIELD_RE = re.compile(
        # 支持 `table`.`field` 限定的聚合字段，捕获最后一个标识符（真正的字段名）
        # 例如 SUM(`orders`.`amount`) → amount（而不是误捕获表名 orders）
        r"\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\(\s*(?:`?[A-Za-z_][A-Za-z0-9_]*`?\s*\.\s*)*`?(?P<field>[A-Za-z_][A-Za-z0-9_]*)`?",
        re.IGNORECASE,
    )

    def _extract_referenced_fields(sql: str) -> set:
        """提取 SQL 中引用的所有字段名"""
        fields = set()
        # 排除常见 SQL 关键字
        sql_keywords = {
            "as", "by", "in", "is", "not", "on", "or", "and", "null", "like",
            "asc", "desc", "sum", "count", "avg", "min", "max", "distinct",
            "between", "group", "order", "limit", "having", "where", "select",
            "from", "join", "inner", "left", "right", "outer", "full",
        }

        # 提取 FROM / JOIN 的表名（用于排除）
        table_names = set()
        from_pattern = re.compile(r"\bFROM\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", re.IGNORECASE)
        join_pattern = re.compile(r"\b(?:INNER|LEFT|RIGHT|FULL|OUTER|CROSS)?\s*JOIN\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", re.IGNORECASE)
        for m in from_pattern.finditer(sql):
            table_names.add(m.group(1).lower())
        for m in join_pattern.finditer(sql):
            table_names.add(m.group(1).lower())

        # 提取 SELECT 中所有字段
        select_match = re.search(r"\bSELECT\s+(.*?)(?:\bFROM\b|$)",
                                 sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_clause = select_match.group(1)
            # 提取聚合函数中的字段（如 SUM(x), COUNT(*), COUNT(DISTINCT x)）
            for m in _AGG_FIELD_RE.finditer(select_clause):
                fname = m.group("field").lower()
                if fname and fname != "*" and fname not in sql_keywords:
                    fields.add(fname)
            # 提取普通字段（处理 `table.field`、`field`、`field AS alias`）
            # 先移除聚合函数部分（避免误提取）
            cleaned = re.sub(r"\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\([^)]*\)", "", select_clause)
            # 提取 `table.field` 中的 field 字段（忽略 table 前缀）
            for m in re.finditer(r"`?([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*`?([A-Za-z_][A-Za-z0-9_]*)`?", cleaned):
                fname = m.group(2).lower()  # 只取 .field 部分
                if fname and fname not in sql_keywords and fname != "*":
                    fields.add(fname)
            # 提取纯字段名（不在 .field 中，且不是 AS 别名）
            # 先去掉 AS 别名
            cleaned_no_alias = re.sub(r"\bAS\s+`?[A-Za-z_][A-Za-z0-9_]*`?", "", cleaned, flags=re.IGNORECASE)
            # 去掉已经处理的 .field
            cleaned_no_dot = re.sub(r"`?[A-Za-z_][A-Za-z0-9_]*\s*\.\s*`?[A-Za-z_][A-Za-z0-9_]*`?", "", cleaned_no_alias)
            for f in re.findall(r"`?([A-Za-z_][A-Za-z0-9_]*)`?", cleaned_no_dot):
                fname = f.lower()
                if fname and fname not in sql_keywords and fname != "*" and fname not in table_names:
                    fields.add(fname)

        # 提取 WHERE/GROUP BY/ORDER BY/ON/HAVING 中字段（排除表名）
        for kw in ("WHERE", "GROUP BY", "ORDER BY", "ON", "HAVING"):
            pat = re.compile(rf"\b{kw}\s+(.*?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
                             re.IGNORECASE | re.DOTALL)
            m = pat.search(sql)
            if m:
                # 移除聚合函数
                cleaned = re.sub(r"\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\([^)]*\)", "", m.group(1))
                # 移除 AS 别名
                cleaned = re.sub(r"\bAS\s+`?[A-Za-z_][A-Za-z0-9_]*`?", "", cleaned, flags=re.IGNORECASE)
                # 提取 .field 中的字段
                for m2 in re.finditer(r"`?([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*`?([A-Za-z_][A-Za-z0-9_]*)`?", cleaned):
                    fname = m2.group(2).lower()
                    if fname and fname not in sql_keywords:
                        fields.add(fname)
                # 提取纯字段名
                cleaned_no_dot = re.sub(r"`?[A-Za-z_][A-Za-z0-9_]*\s*\.\s*`?[A-Za-z_][A-Za-z0-9_]*`?", "", cleaned)
                for f in re.findall(r"`?([A-Za-z_][A-Za-z0-9_]*)`?", cleaned_no_dot):
                    fname = f.lower()
                    if fname and fname not in sql_keywords and fname not in table_names:
                        fields.add(fname)

        return fields

    def _build_schema_field_map(state) -> dict:
        """构建 {field_name_lower: [table1, table2]} 的映射"""
        schema = state.get("schema", {}) or {}
        columns_dict = schema.get("columns", {}) or {}
        field_map = {}
        for table, cols in columns_dict.items():
            if not isinstance(cols, list):
                continue
            for col in cols:
                if not isinstance(col, dict):
                    continue
                fname = (col.get("name") or col.get("COLUMN_NAME") or "").lower()
                if fname:
                    field_map.setdefault(fname, []).append(table)
        return field_map

    def validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SQL VALIDATOR NODE INPUT ==========")
        print(f"sql: {state.get('sql', '')}")
        print(f"===============================================\n")

        sql = state.get("sql", "")
        sql_upper = sql.upper()
        errors = []
        warnings = []

        # 1. 危险关键字检查
        for keyword in DANGEROUS_KEYWORDS:
            if re.search(rf"\b{keyword}\b", sql_upper):
                errors.append(f"不允许使用危险关键字: {keyword}")

        # 2. Schema 字段存在性验证
        schema = state.get("schema", {}) or {}
        if schema and schema.get("columns"):
            field_map = _build_schema_field_map(state)
            ref_fields = _extract_referenced_fields(sql)
            # 排除常见 SQL 关键字
            sql_keywords = {
                "as", "by", "in", "is", "not", "on", "or", "and", "null", "like",
                "asc", "desc", "sum", "count", "avg", "min", "max", "distinct",
                "between", "group", "order", "limit", "having", "where", "select",
                "from", "join", "inner", "left", "right", "outer", "full",
            }
            unknown_fields = ref_fields - sql_keywords
            unknown_fields = {f for f in unknown_fields if f and not f.isdigit()}
            for fname in unknown_fields:
                # 字段在 schema 中找不到，可能是 LLM 幻觉
                if fname not in field_map:
                    warnings.append({
                        "type": "UNKNOWN_FIELD",
                        "field": fname,
                        "message": f"字段 `{fname}` 在数据库中不存在",
                    })

        elapsed = time.time() - start_time

        print(f"\n========== SQL VALIDATOR NODE OUTPUT ==========")
        print(f"valid: {len(errors) == 0}")
        print(f"errors: {errors}")
        print(f"warnings: {warnings}")
        print(f"[TIMER] SQL Validator: {elapsed:.4f}s")
        print(f"===============================================\n")

        return {
            "validation_result": {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings
            },
            "node_timings": {"sql_validator": elapsed}
        }

    return validator_node


def create_result_validator_node():
    """创建 RESULT VALIDATOR 节点"""

    def validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== RESULT VALIDATOR NODE INPUT ==========")
        print(f"execution_result: {str(state.get('execution_result', []))[:300]}")
        print(f"=================================================\n")

        result = state.get("execution_result")

        if result is None:
            elapsed = time.time() - start_time
            print(f"\n========== RESULT VALIDATOR NODE OUTPUT ==========")
            print(f"validation_passed: False (result is None)")
            print(f"[TIMER] Result Validator: {elapsed:.4f}s")
            print(f"=================================================\n")
            return {"validation_passed": False, "node_timings": {"result_validator": elapsed}}

        if isinstance(result, list):
            passed = len(result) > 0
        elif isinstance(result, dict):
            passed = len(result) > 0
        else:
            passed = True

        elapsed = time.time() - start_time

        print(f"\n========== RESULT VALIDATOR NODE OUTPUT ==========")
        print(f"validation_passed: {passed}")
        print(f"[TIMER] Result Validator: {elapsed:.4f}s")
        print(f"=================================================\n")

        return {"validation_passed": passed, "node_timings": {"result_validator": elapsed}}

    return validator_node
