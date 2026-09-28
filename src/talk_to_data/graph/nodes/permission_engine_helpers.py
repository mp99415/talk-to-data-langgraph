"""
Permission Engine 辅助函数
"""
import re


def inject_where_into_sql(sql: str, conditions: list) -> str:
    """
    把缺失的 WHERE 条件强制注入到 SQL 中。

    参数:
        sql: 原始 SQL
        conditions: list of (table, field, op, value) 元组

    行为:
        - 如果 SQL 已有 WHERE，在末尾追加 AND
        - 如果没有 WHERE，插入到 FROM/JOIN 之后、GROUP BY/HAVING/ORDER BY/LIMIT 之前
        - value 会被单引号包裹并转义
    """
    if not sql or not conditions:
        return sql
    parts = []
    for cond in conditions:
        if len(cond) == 4:
            table, field, op, value = cond
        else:
            continue
        # 转义单引号
        safe_val = str(value).replace("'", "''")
        # 字段引用：表名.字段 或 字段
        if table:
            field_ref = f"`{table}`.`{field}`"
        else:
            field_ref = f"`{field}`"
        parts.append(f"{field_ref} {op} '{safe_val}'")
    if not parts:
        return sql
    extra = " AND ".join(parts)
    upper_sql = sql.upper()
    if ' WHERE ' in upper_sql:
        # 在 WHERE 后追加 AND
        return re.sub(r'(\bWHERE\b)', r'\1 ' + extra + ' AND', sql, count=1, flags=re.IGNORECASE)
    # 没有 WHERE：插入到 FROM/JOIN 之后、GROUP BY 等子句之前
    insert_before = None
    for kw in (" GROUP BY ", " HAVING ", " ORDER BY ", " LIMIT "):
        idx = upper_sql.find(kw)
        if idx >= 0:
            insert_before = idx
            break
    if insert_before is not None:
        return sql[:insert_before] + f" WHERE {extra} " + sql[insert_before:]
    # 否则追加到末尾
    return sql.rstrip().rstrip(';') + f" WHERE {extra}"


# 兜底用户引用字段名（与 user_reference_config 一致）
_SQL_FALLBACK_OWNER_FIELDS = {
    "sales_id", "owner_id", "creator_id", "assignee_id", "approver_id",
    "agent_id", "created_by", "updated_by", "manager_id",
    "created_by_id", "updated_by_id",
}
# 用户引用关键词（与 user_reference_config.DEFAULT_CONFIG.user_reference_keywords 对齐）
_SQL_USER_REF_KEYWORDS = {
    "我", "我的", "我负责", "我名下", "我经手", "我签订", "我对接",
    "我自己", "归属于我", "分配给我", "属于我", "我签的", "我谈的",
    "我开的", "我做的",
}


def _is_user_reference_value(val: str, user_username: str, user_name: str) -> bool:
    """
    判断一个 SQL 字面量值是否"指代当前用户但未正确替换"。

    包括:
      - 用户引用关键词完全匹配（"我的"、"我自己" 等）
      - 以 "我的" 开头后接任何后缀（"我的客户"、"我的订单" 等）
      - 占位符（${current_user_id} 等）
      - 用户名/姓名（zhangsan、zhangsan、"张三" 等）
    """
    if not val:
        return False
    if val.startswith("${"):
        return True
    # 完全匹配关键词
    if val in _SQL_USER_REF_KEYWORDS:
        return True
    # 以"我的"开头的变体（"我的客户"/"我的订单" 等）
    for kw in _SQL_USER_REF_KEYWORDS:
        if val.startswith(kw):
            return True
    # 用户名/姓名
    for v in (user_username, user_name):
        if v and v == val:
            return True
    return False


def enforce_user_reference_in_sql(
    sql: str,
    current_user_id: str,
    user_username: str = "",
    user_name: str = "",
) -> str:
    """
    SQL 字符串层兜底纠正：直接扫描 SQL 字符串中所有用户引用字段的字面量值，
    把"我的"/"我自己"/"我的客户"/username/name/${占位符} 等错误值替换为真实 user_id。

    应对场景：semantic 层 filter 已纠正，但 LLM 生成 SQL 时仍可能注入
    `customers.sales_id = '我的'` / `customers.sales_id = '我的客户'` 这种字面量值
    （特别是在多表 JOIN 时）。

    参数:
        sql: 原始 SQL 字符串
        current_user_id: 当前用户的真实 user_id（如 "1004"）
        user_username: 当前用户名（如 "wangzong"）
        user_name: 当前用户姓名（如 "王总"）

    返回:
        纠正后的 SQL（如未发现错误值，原样返回）
    """
    if not sql or not current_user_id:
        return sql

    # 构建正则：匹配 "`<table>.`<field>` <op> '<bad_value>'" 或 "<field> <op> '<bad_value>'"
    # field 必须在 _SQL_FALLBACK_OWNER_FIELDS 内
    # 操作符支持 = / != / <> / < / <= / > / >=
    fields_pattern = "|".join(re.escape(f) for f in _SQL_FALLBACK_OWNER_FIELDS)

    # 匹配模式：`?<table>.?`<field>`? <op> '?<any_value>'?
    pattern = re.compile(
        rf"(`?(?:\w+\.)?`?)({fields_pattern})(`?\s*(?:!=|<>|=|>=|<=|>|<)\s*)'([^']*)'",
        re.IGNORECASE
    )

    def _replace(m):
        prefix = m.group(1)
        field = m.group(2)
        op = m.group(3)
        value = m.group(4)
        # 判断 value 是否指代当前用户但未正确替换
        if _is_user_reference_value(value, user_username, user_name):
            new_value = current_user_id
            print(f"[DEBUG][SQL 字面量纠正] {prefix}{field}{op}'{value}' → '{new_value}'")
            return f"{prefix}{field}{op}'{new_value}'"
        return m.group(0)

    new_sql, count = pattern.subn(_replace, sql)
    if count > 0:
        print(f"[INFO][SQL 字面量纠正] 共纠正 {count} 处 user_reference 字面量")
    return new_sql