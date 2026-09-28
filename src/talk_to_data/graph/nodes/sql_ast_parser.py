"""
SQL AST Parser 节点
用于解析和规范化 SQL
"""

import re
import json
from typing import Dict, Any, List, Optional


def create_sql_ast_parser_node():
    """创建 SQL AST Parser 节点"""

    def sql_ast_parser_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 SQL 并生成 AST

        输入:
            - sql: 原始 SQL 语句

        输出:
            - normalized_sql: 规范化后的 SQL
            - ast: SQL 抽象语法树
            - is_valid: 是否有效
            - error_code: 错误代码
            - error_message: 错误信息
            - violations: 违规列表
        """
        print("\n========== SQL AST PARSER NODE INPUT ==========")
        print(f"sql: {state.get('sql', '')}")
        print("================================================\n")

        sql = state.get("sql", "")

        if not sql:
            return {
                "normalized_sql": "",
                "ast": {},
                "is_valid": False,
                "error_code": "EMPTY_SQL",
                "error_message": "SQL 为空",
                "violations": []
            }

        # 规范化 SQL
        normalized_sql = normalize_sql(sql)

        # 提取 SQL 基本信息
        tables = extract_sql_tables(normalized_sql)
        select_fields = extract_select_fields(normalized_sql)

        # 验证 SQL 基本有效性
        violations = validate_sql_basic(normalized_sql)

        is_valid = len(violations) == 0

        ast = {
            "normalized_sql": normalized_sql,
            "tables": tables,
            "select_fields": select_fields,
            "has_aggregate": contains_aggregate(normalized_sql)
        }

        print("\n========== SQL AST PARSER NODE OUTPUT ==========")
        print(f"normalized_sql: {normalized_sql}")
        print(f"is_valid: {is_valid}")
        print(f"violations count: {len(violations)}")
        print("================================================\n")

        return {
            "normalized_sql": normalized_sql,
            "ast": ast,
            "is_valid": is_valid,
            "violations": violations
        }

    return sql_ast_parser_node


def normalize_sql(sql: str) -> str:
    """规范化 SQL 语句"""
    if not sql:
        return ""

    # 移除 markdown 代码块标记
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE)
    sql = sql.replace("```", "")

    # 移除行内注释
    sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)

    # 规范化空白字符
    sql = re.sub(r"\s+", " ", sql)

    # 移除末尾的分号
    sql = re.sub(r";\s*$", "", sql)

    return sql.strip()


def extract_sql_tables(sql: str) -> List[str]:
    """提取 SQL 中的表名"""
    tables = []

    # FROM 子句
    from_pattern = re.compile(
        r"\bFROM\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
        re.IGNORECASE
    )
    for match in from_pattern.finditer(sql):
        tables.append(match.group(1))

    # JOIN 子句
    join_pattern = re.compile(
        r"\b(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+|OUTER\s+|CROSS\s+)?JOIN\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
        re.IGNORECASE
    )
    for match in join_pattern.finditer(sql):
        tables.append(match.group(1))

    return list(dict.fromkeys(tables))  # 去重保持顺序


def extract_select_fields(sql: str) -> List[str]:
    """提取 SELECT 字段"""
    match = re.search(r"\bSELECT\s+(.*?)(?:\bFROM\b|$)", sql, re.IGNORECASE)
    if not match:
        return []

    select_clause = match.group(1)
    fields = [f.strip() for f in select_clause.split(",")]
    return fields


def contains_aggregate(sql: str) -> bool:
    """检查是否包含聚合函数"""
    return bool(re.search(r"\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(", sql, re.IGNORECASE))


def validate_sql_basic(sql: str) -> List[Dict[str, str]]:
    """验证 SQL 基本有效性"""
    violations = []

    sql_upper = sql.upper()

    # 检查是否为空
    if not sql.strip():
        violations.append({
            "type": "EMPTY_SQL",
            "message": "SQL 为空",
            "table": "",
            "field": ""
        })
        return violations

    # 检查是否为 SELECT 语句
    if not re.search(r"\bSELECT\b", sql_upper):
        violations.append({
            "type": "NON_SELECT_SQL",
            "message": "只允许 SELECT 查询语句",
            "table": "",
            "field": ""
        })

    # 检查是否包含危险关键字
    dangerous_keywords = [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
        "TRUNCATE", "CREATE", "GRANT", "REVOKE"
    ]
    for keyword in dangerous_keywords:
        if re.search(rf"\b{keyword}\b", sql_upper):
            violations.append({
                "type": "FORBIDDEN_STATEMENT",
                "message": f"不允许使用 {keyword} 语句",
                "table": "",
                "field": ""
            })

    # 检查是否为 SELECT *
    if re.search(r"\bSELECT\s+\*", sql_upper):
        violations.append({
            "type": "SELECT_STAR",
            "message": "请指定具体的查询字段，避免使用 SELECT *",
            "table": "",
            "field": ""
        })

    # 检查是否有多条语句
    if sql.count(";") > 1:
        violations.append({
            "type": "MULTI_STATEMENT",
            "message": "不允许执行多条 SQL 语句",
            "table": "",
            "field": ""
        })

    return violations
