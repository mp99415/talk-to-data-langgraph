"""
Permission Engine 节点
用于验证 SQL 是否符合权限策略
"""

import re
from typing import Dict, Any, List, Optional


def create_permission_engine_node():
    """创建 Permission Engine 节点"""

    def permission_engine_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        权限引擎验证

        输入:
            - sql: SQL 语句
            - ast: SQL AST
            - permissions: 权限信息
            - field_permissions: 字段权限信息
            - row_policies: 行级策略

        输出:
            - status: 状态
            - authorized: 是否授权
            - authorized_sql: 授权后的 SQL
            - violations: 违规列表
            - applied_policies: 应用的策略
            - permission_result: 权限结果
        """
        print("\n========== PERMISSION ENGINE NODE INPUT ==========")
        print(f"sql: {state.get('sql', '')}")
        print(f"permissions: {len(state.get('permissions', []))} items")
        print(f"field_permissions: {len(state.get('field_permissions', []))} items")
        print("====================================================\n")

        sql = state.get("sql", "")
        ast = state.get("ast", {})
        permissions = state.get("permissions", [])
        field_permissions = state.get("field_permissions", [])
        row_policies = state.get("row_policies", [])

        # 从 user_info 提取 user_id / region（用于 row policy 占位符替换）
        user_info = state.get("user_info", [])
        current_user_id = None
        current_user_region = None
        if isinstance(user_info, list) and user_info:
            current_user_id = str(user_info[0].get("user_id") or "")
            current_user_region = user_info[0].get("region")

        # 提取 SQL 中的表
        tables = ast.get("tables", []) or extract_tables_from_sql(sql)

        # 验证表级权限
        table_violations = validate_table_permissions(tables, permissions)

        # 验证字段权限
        field_violations = validate_field_permissions(sql, field_permissions, tables)

        # 合并所有违规
        all_violations = table_violations + field_violations

        # ========== SQL 字面量兜底纠正（先纠正，再做冲突检测） ==========
        # 即使 semantic 层 filter 已纠正，LLM 生成 SQL 时仍可能注入
        # `customers.sales_id = '我的'` / `sales_id = '${current_user_id}'` /
        # `sales_id != '我的'` 等字面量值。这里先纠正这些字面量值，再做权限冲突检测，
        # 否则 `sales_id != '我的'` 检测不到（val='我的' 不等于 real_id），
        # 修正为 `sales_id != '1004'` 后才能被识别为"反向查他人"。
        if sql and current_user_id:
            try:
                from .permission_engine_helpers import enforce_user_reference_in_sql
                _corrected = enforce_user_reference_in_sql(
                    sql,
                    current_user_id=str(current_user_id),
                    user_username=str(user_info[0].get("username") or "") if user_info else "",
                    user_name=str(user_info[0].get("name") or "") if user_info else "",
                )
                if _corrected and _corrected != sql:
                    print(f"[INFO] SQL 字面量兜底纠正完成")
                    sql = _corrected
            except Exception as e:
                print(f"[DEBUG] SQL 字面量兜底纠正异常: {str(e)}")

        # ========== 字段级冲突检测：owner/region 字段只能过滤"自己" ==========
        # 策略语义：
        #   - owner 类字段（如 sales_id）仅允许过滤当前用户 ID，其他值拒绝
        #   - region 字段仅允许过滤当前用户所在 region，其他值拒绝
        # 触发时机：SQL 执行前拦截，避免用户查他人拿到 0 行数据但不知原因
        # 先用 filters 检测（语义层），再用 SQL 正则兜底（应对 apply_row_policies 改写 SQL 的情况）
        user_scope = state.get("user_scope") or None
        field_violation = _check_owner_region_field_conflict(
            sql=sql,
            query_state=state.get("query_state", {}) or {},
            semantic_result=state.get("semantic_result", {}) or {},
            row_policies=row_policies,
            user_id=current_user_id,
            user_region=current_user_region,
            user_scope=user_scope,
        )
        if field_violation:
            all_violations.append(field_violation)

        # 应用行级策略（如果需要）
        authorized_sql = apply_row_policies(
            sql, row_policies, tables,
            user_id=current_user_id,
            user_region=current_user_region
        )

        authorized = len(all_violations) == 0

        permission_result = {
            "status": "AUTHORIZED" if authorized else "FORBIDDEN",
            "authorized": authorized,
            "authorized_sql": authorized_sql if authorized else "",
            "violations": all_violations,
            "applied_policies": [],
            "checked_tables": [{"table": t, "checked": True} for t in tables],
            "checked_fields": [],
            "checked_joins": [],
            "error_message": ""
        }

        print("\n========== PERMISSION ENGINE NODE OUTPUT ==========")
        print(f"authorized: {authorized}")
        print(f"violations count: {len(all_violations)}")
        print(f"checked_tables: {tables}")
        print("====================================================\n")

        # 关键修复：把授权 SQL 写到 sql 字段，避免 LangGraph state 传递丢失
        sql_for_next = authorized_sql if authorized else ""

        # 在 permission_engine 阶段完成 where_conditions 兜底注入
        # sql_generator 有时丢失 query_plan.where_conditions，需要从 sql_query_plan 注入
        sql_query_plan_wcs = []
        try:
            _sqp = state.get("sql_query_plan", {}) or {}
            if isinstance(_sqp, dict):
                sql_query_plan_wcs = _sqp.get("where_conditions") or []
        except Exception:
            pass
        print(f"[DEBUG permission_engine] before: authorized_sql={authorized_sql[:200]!r}")
        print(f"[DEBUG permission_engine] sql_query_plan_wcs count={len(sql_query_plan_wcs)}")
        if authorized_sql and sql_query_plan_wcs:
            try:
                from .permission_engine_helpers import (
                    inject_where_into_sql,
                    _is_user_reference_value,
                )
                missing = []
                for wc in sql_query_plan_wcs:
                    if not isinstance(wc, dict):
                        continue
                    wc_field = (wc.get("field") or "").strip()
                    wc_table = (wc.get("table") or "").strip()
                    wc_op = (wc.get("operator") or "=").strip()
                    wc_val = wc.get("physical_value") or wc.get("value")
                    if not wc_field or wc_val is None or wc_val == "":
                        continue
                    if wc.get("type", "").startswith("time"):
                        continue
                    # 兜底纠正：用户引用字段上的 wc_val 是错误字面量（"我的"/占位符/username/name）时，
                    # 替换为真实 user_id，避免注入 SQL 后无法执行
                    wc_val_str = str(wc_val)
                    if current_user_id and _is_user_reference_value(
                        wc_val_str,
                        str(user_info[0].get("username") or "") if user_info else "",
                        str(user_info[0].get("name") or "") if user_info else "",
                    ):
                        new_val = str(current_user_id)
                        print(f"[INFO] where_conditions wc_val 兜底纠正: {wc_field} {wc_val_str!r} → {new_val!r}")
                        wc_val = new_val
                    # 检测 SQL 中是否已存在该字段的过滤（任何表前缀或无前缀都算）
                    any_pattern = rf"(?:(?:`?\w+`?\.`?{re.escape(wc_field)}`?)|`?{re.escape(wc_field)}`?)\s*{re.escape(wc_op)}\s*'?"
                    if re.search(any_pattern, authorized_sql, re.IGNORECASE):
                        print(f"[DEBUG] wc already present, skip: {wc_field}={wc_val}")
                        continue  # 已经有该条件，跳过
                    print(f"[DEBUG] wc missing, will add: ({wc_table}, {wc_field}, {wc_op}, {wc_val})")
                    missing.append((wc_table, wc_field, wc_op, wc_val))
                if missing:
                    injected_sql = inject_where_into_sql(authorized_sql, missing)
                    if injected_sql and injected_sql != authorized_sql:
                        print(f"[INFO] where_conditions 兜底注入: {missing}")
                        authorized_sql = injected_sql
            except Exception as e:
                print(f"[DEBUG] where_conditions 兜底注入异常: {str(e)}")

        # 关键修复：把授权 SQL 写到 sql 字段，避免 LangGraph state 传递丢失
        sql_for_next = authorized_sql if authorized else ""

        return {
            "permission_result": permission_result,
            "authorized": authorized,
            "authorized_sql": authorized_sql if authorized else "",
            "sql": sql_for_next,  # 让后续 sql_executor 直接拿到授权 SQL
            "security_result": {"allowed": authorized}
        }

    return permission_engine_node


def extract_tables_from_sql(sql: str) -> List[str]:
    """从 SQL 中提取表名"""
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
        r"\b(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+|OUTER\s+)?JOIN\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
        re.IGNORECASE
    )
    for match in join_pattern.finditer(sql):
        tables.append(match.group(1))

    return list(dict.fromkeys(tables))


def validate_table_permissions(tables: List[str], permissions: List[Dict]) -> List[Dict]:
    """验证表级权限"""
    violations = []

    if not tables:
        return violations

    # 构建权限表
    allowed_tables = set()
    for perm in permissions:
        resource = perm.get("resource", "")
        effect = perm.get("effect", "")
        action = perm.get("action", "")

        if effect == "ALLOW" and action in ("read", "export"):
            allowed_tables.add(resource.lower())

    # 检查每个表是否有权限
    for table in tables:
        table_lower = table.lower()
        if allowed_tables and table_lower not in allowed_tables:
            violations.append({
                "code": "TABLE_NOT_ALLOWED",
                "message": f"表 {table} 没有访问权限",
                "table": table,
                "field": "",
                "usage": "read"
            })

    return violations


def validate_field_permissions(sql: str, field_permissions: List[Dict], tables: List[str]) -> List[Dict]:
    """验证字段权限"""
    violations = []

    if not field_permissions:
        return violations

    # 构建字段权限映射
    field_perm_map = {}
    for fp in field_permissions:
        table = fp.get("table_name", "").lower()
        field = fp.get("field_name", "").lower()
        can_read = fp.get("can_read", 0) == 1

        key = f"{table}.{field}"
        field_perm_map[key] = can_read

    # 提取 SELECT 中的字段
    select_match = re.search(r"\bSELECT\s+(.*?)(?:\bFROM\b|$)", sql, re.IGNORECASE)
    if not select_match:
        return violations

    select_clause = select_match.group(1)
    # 解析字段（简化版）
    fields = [f.strip().split()[-1] for f in select_clause.split(",")]

    for field in fields:
        # 检查是否为 qualified 字段
        if "." in field:
            table, col = field.split(".", 1)
            table = table.lower()
            col = col.lower().strip("`")
            key = f"{table}.{col}"
        else:
            # 未限定的字段，检查所有表
            col = field.lower().strip("`")
            key = None
            for t in tables:
                potential_key = f"{t.lower()}.{col}"
                if potential_key in field_perm_map:
                    key = potential_key
                    break

        if key and key in field_perm_map:
            if not field_perm_map[key]:
                violations.append({
                    "code": "FIELD_NOT_ALLOWED",
                    "message": f"字段 {field} 没有读取权限",
                    "table": "",
                    "field": field,
                    "usage": "read"
                })

    return violations


def apply_row_policies(sql: str, row_policies: List[Dict], tables: List[str],
                       user_id: Optional[str] = None,
                       user_region: Optional[str] = None) -> str:
    """应用行级策略

    将 data_policies 中的 ROW 策略转换为 SQL WHERE 条件并注入。
    支持占位符替换：${user.id} -> user_id，${user.region} -> user_region。
    """
    if not row_policies or not sql:
        return sql

    where_clauses = []
    seen_clauses = set()  # 去重：相同 (field, operator, value) 不重复追加
    for policy in row_policies:
        if not isinstance(policy, dict):
            continue
        if policy.get('policy_type') != 'ROW':
            continue
        if not policy.get('enabled', 1):
            continue

        field = policy.get('condition_field', '')
        operator = policy.get('condition_operator', '=')
        raw_value = policy.get('condition_value', '')
        if not field:
            continue

        # 占位符替换
        value = raw_value
        if '${user.id}' in value:
            if not user_id:
                continue
            value = value.replace('${user.id}', str(user_id))
        elif '${user.region}' in value:
            if not user_region:
                continue
            value = value.replace('${user.region}', str(user_region))

        # 转义单引号
        safe_value = str(value).replace("'", "''")
        # 如果 SQL 涉及多表 JOIN，给字段加表名前缀避免歧义
        if tables and len(tables) > 1:
            table = tables[0] if tables[0] != 'orders' else (tables[1] if len(tables) > 1 else tables[0])
            clause = f"`{table}`.`{field}` {operator} '{safe_value}'"
        else:
            clause = f"`{field}` {operator} '{safe_value}'"
        clause_key = (field, operator, str(value))
        if clause_key in seen_clauses:
            print(f"[DEBUG] skip duplicate clause: {clause}")
            continue
        seen_clauses.add(clause_key)
        where_clauses.append(clause)

    if not where_clauses:
        return sql

    # 注入到 SQL 的 WHERE 子句
    # 注意：必须保证 WHERE 在 FROM/JOIN 之后、GROUP BY/HAVING/ORDER BY/LIMIT 之前
    # 否则 `... GROUP BY ... WHERE ...` 是非法 SQL，MySQL 会忽略 WHERE
    extra = " AND ".join(where_clauses)
    upper_sql = sql.upper()

    if ' WHERE ' in upper_sql:
        # 已有 WHERE：追加 AND
        sql = re.sub(r'(\bWHERE\b)', r'\1 ' + extra + ' AND', sql, count=1, flags=re.IGNORECASE)
    else:
        # 没有 WHERE：插到 FROM/JOIN 子句之后，GROUP BY/HAVING/ORDER BY/LIMIT 之前
        # 优先匹配 GROUP BY/HAVING/ORDER BY/LIMIT
        insert_before = None
        for kw in (" GROUP BY ", " HAVING ", " ORDER BY ", " LIMIT "):
            idx = upper_sql.find(kw)
            if idx >= 0:
                insert_before = idx
                break
        if insert_before is not None:
            sql = sql[:insert_before] + f" WHERE {extra} " + sql[insert_before:]
        else:
            # 没有这些子句，直接末尾加
            sql = sql.rstrip().rstrip(';') + f" WHERE {extra}"

    return sql


# owner 类字段（人员引用字段）的字段名集合，用于冲突检测
_OWNER_FIELD_NAMES = {
    "sales_id", "owner_id", "creator_id", "assignee_id", "approver_id",
    "agent_id", "created_by", "manager_id", "created_by_id", "updated_by_id",
    "user_id", "operator_id",
}
# region 字段名集合
_REGION_FIELD_NAMES = {"region", "area", "zone"}


def _infer_field_kind(field_name: str) -> str:
    """根据字段名推断字段类别：owner / region / other"""
    if not field_name:
        return "other"
    if field_name in _REGION_FIELD_NAMES:
        return "region"
    if field_name in _OWNER_FIELD_NAMES:
        return "owner"
    return "other"


def _resolve_allowed_user_ids(
    user_scope: Optional[Dict[str, Any]],
    current_user_id: str,
    row_policies: Optional[List[Dict]] = None,
) -> set:
    """
    根据 user_scope 计算可允许查询的 user_id 集合。

    user_scope 格式:
      - None: 兼容旧行为
        - 如果 row_policies 为空（无行级策略），降级为 all（无限制）
        - 否则只允许当前用户
      - {"scope_type": "self"}: 只允许当前用户
      - {"scope_type": "all"}: 允许任何 user_id（admin）
      - {"scope_type": "team"|"department", "allowed_user_ids": ["1001", "1002", ...]}:
        允许指定列表中的 user_id

    返回: set[str] 或 None（None = 不限制）
    """
    if not user_scope:
        # 兼容：user_scope 没配置（DB 不可达或未启用 scope）
        # 如果用户角色没有任何 row_policies，降级为 all（无限制），允许查他人
        if not row_policies:
            return None  # type: ignore[return-value]
        return {str(current_user_id)}
    scope_type = user_scope.get("scope_type", "self")
    if scope_type == "all":
        # admin: 允许任何 user_id，用特殊标记（None 表示不限制）
        return None  # type: ignore[return-value]
    if scope_type == "self":
        return {str(current_user_id)}
    # team / department
    allowed = user_scope.get("allowed_user_ids") or []
    if not allowed:
        return {str(current_user_id)}
    return {str(x) for x in allowed} | {str(current_user_id)}


def _describe_scope(
    user_scope: Optional[Dict[str, Any]],
    current_user_id: str,
) -> str:
    """生成可查询范围的人类可读描述"""
    if not user_scope:
        return f"仅自己（user_id={current_user_id}）"
    scope_type = user_scope.get("scope_type", "self")
    if scope_type == "all":
        return "全部用户"
    if scope_type == "self":
        return f"仅自己（user_id={current_user_id}）"
    allowed = user_scope.get("allowed_user_ids") or []
    if allowed:
        sample = ", ".join(str(x) for x in allowed[:5])
        more = f" 等 {len(allowed)} 人" if len(allowed) > 5 else ""
        return f"范围内用户（{scope_type}）: {sample}{more}"
    return f"仅自己（user_id={current_user_id}）"


def _check_owner_region_field_conflict(
    sql: str,
    query_state: Dict[str, Any],
    semantic_result: Dict[str, Any],
    row_policies: List[Dict],
    user_id: Optional[str] = None,
    user_region: Optional[str] = None,
    user_scope: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    字段级冲突检测。

    规则：
      - owner 字段（sales_id 等）的过滤值必须在 user_scope.allowed_user_ids 内
      - region 字段只允许过滤当前用户所在 region；其他值 → FORBIDDEN
      - 没有 WHERE 过滤（不指定）时，让 apply_row_policies 走默认注入流程（不在这里拒绝）
    返回 None 表示通过；返回 dict 表示违规详情（permission_engine 收到后会标 FORBIDDEN）。

    user_scope 格式:
      {
        "scope_type": "self" | "team" | "department" | "all",
        "allowed_user_ids": ["1001", "1002", ...],  # 当前用户可查询的 user_id 列表
      }

    兼容:
      - user_scope=None 或 scope_type='self' → 只允许 current_user_id（默认行为）
      - scope_type='all' → 允许任何 user_id（admin）
      - scope_type='team'/'department' → 仅允许 allowed_user_ids 内
    """
    try:
        # 1. 收集所有涉及的 owner/region 字段名（来自 row_policies 的 condition_field）
        #    因为 row_policies 已经声明了哪些字段是 owner/region 维度，由 DBA/运维配置
        owner_fields: set = set()
        region_fields: set = set()
        for p in (row_policies or []):
            if not isinstance(p, dict):
                continue
            cf = (p.get("condition_field") or "").strip()
            cv = (p.get("condition_value") or "").strip()
            if not cf:
                continue
            # 只关心以 ${user.id} 结尾的策略（owner 类）
            kind = _infer_field_kind(cf)
            if cv in ("${user.id}", "${user.id}"):
                owner_fields.add(cf)
            elif cv in ("${user.region}", "${user.region}"):
                region_fields.add(cf)
            elif kind == "owner":
                owner_fields.add(cf)
            elif kind == "region":
                region_fields.add(cf)
        # 兜底：基于字段名启发式识别 owner/region 字段，覆盖无 row_policy 的用户角色
        for fname in _OWNER_FIELD_NAMES:
            owner_fields.add(fname)
        for fname in _REGION_FIELD_NAMES:
            region_fields.add(fname)

        # 2. 从 semantic_result/query_state 抽取实际生效的 owner/region 过滤值
        #    优先级：query_state.filters（最新）→ semantic_result.filters → sql（正则）
        candidates: List[Dict[str, Any]] = []
        qs_filters = query_state.get("filters", []) if isinstance(query_state, dict) else []
        sem_filters = semantic_result.get("filters", []) if isinstance(semantic_result, dict) else []
        # 去重（query_state 和 semantic_result 可能是同一份引用）
        seen = set()
        for f in (qs_filters + sem_filters):
            if not isinstance(f, dict):
                continue
            key = id(f)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(f)

        # 3. 检查每个 owner/region 字段
        for f in candidates:
            field = (f.get("field") or "").strip()
            if not field:
                continue
            kind = _infer_field_kind(field)
            if kind not in ("owner", "region"):
                continue
            # 取最可靠的物理值
            v_raw = f.get("physical_value") or f.get("value") or ""
            v = str(v_raw).strip()
            if not v:
                # 没有过滤值（不是问题里要查某人的场景），让 apply_row_policies 默认注入当前用户
                continue
            # 占位符残留，说明上游未替换，放行让 apply_row_policies 处理
            if v.startswith("${"):
                continue
            if kind == "owner":
                if not user_id:
                    # 没有当前用户上下文，放行
                    continue
                op = (f.get("operator") or "=").strip()
                real_id = str(user_id)
                # 计算可允许的 user_id 范围
                allowed_user_ids = _resolve_allowed_user_ids(user_scope, real_id, row_policies)
                # admin (allowed_user_ids=None) 不做限制
                if allowed_user_ids is None:
                    continue
                # 等于他人 → 拒绝（查他人的数据，但允许范围内的人不算"他人"）
                # 不等于当前用户 → 也拒绝（用 != 排除自己反向解读为"查其他人"）
                violation = (
                    (op in ("=", "==") and v not in allowed_user_ids)
                    or (op in ("!=", "<>") and v == real_id)
                )
                if violation:
                    scope_desc = _describe_scope(user_scope, real_id)
                    return {
                        "type": "FIELD_OWNER_FORBIDDEN",
                        "field": field,
                        "table": f.get("table", ""),
                        "operator": op,
                        "value": v,
                        "current_user_id": real_id,
                        "user_scope": user_scope,
                        "message": (
                            f"权限不足：{field} 过滤值 {v} 不在您的可查询范围内"
                            f"（{scope_desc}）"
                        ),
                    }
            elif kind == "region":
                if not user_region:
                    continue
                if v != str(user_region):
                    return {
                        "type": "FIELD_REGION_FORBIDDEN",
                        "field": field,
                        "table": f.get("table", ""),
                        "value": v,
                        "current_user_region": str(user_region),
                        "message": (
                            f"权限不足：{field} 只能过滤当前用户所在区域（{user_region}），"
                            f"不能跨区域查询"
                        ),
                    }

        # 4. SQL 正则兜底：直接扫描 WHERE 中的 owner/region 字段值
        #    应对 query_state.filters 与 sql 不一致（如被 apply_row_policies 改写）的场景
        sql_violation = _scan_sql_owner_region(
            sql, row_policies, user_id, user_region, user_scope
        )
        if sql_violation:
            return sql_violation
        return None
    except Exception as e:
        print(f"[DEBUG] _check_owner_region_field_conflict error: {str(e)}")
        return None


def _scan_sql_owner_region(
    sql: str,
    row_policies: List[Dict],
    user_id: Optional[str] = None,
    user_region: Optional[str] = None,
    user_scope: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    SQL 正则兜底扫描：直接解析 WHERE 子句中的 owner/region 字段值。

    与 _check_owner_region_field_conflict 的区别：
    - 不依赖 query_state/semantic_result，直接从 SQL 字符串提取
    - 用于检测 apply_row_policies 已经改写过 SQL 但 filters 未同步的场景

    user_scope: 同 _check_owner_region_field_conflict，
      - scope_type='all' 跳过 owner 字段冲突检测
      - 其他情况只允许 user_scope.allowed_user_ids 内的值
    """
    if not sql:
        return None
    try:
        # 从 row_policies 推断关注的字段
        owner_fields: set = set()
        region_fields: set = set()
        for p in (row_policies or []):
            if not isinstance(p, dict):
                continue
            cf = (p.get("condition_field") or "").strip()
            cv = (p.get("condition_value") or "").strip()
            if not cf:
                continue
            kind = _infer_field_kind(cf)
            if cv in ("${user.id}", "${user.id}"):
                owner_fields.add(cf)
            elif cv in ("${user.region}", "${user.region}"):
                region_fields.add(cf)
            elif kind == "owner":
                owner_fields.add(cf)
            elif kind == "region":
                region_fields.add(cf)
        # 兜底：当没有任何 row_policies 时（用户角色没有配置策略），
        # 也基于字段名启发式识别 owner/region 字段。否则无 row_policy 的用户
        # （如王总 role=4）无法被保护。
        for fname in _OWNER_FIELD_NAMES:
            owner_fields.add(fname)
        for fname in _REGION_FIELD_NAMES:
            region_fields.add(fname)
        if not owner_fields and not region_fields:
            return None

        # 提取 WHERE 子句
        upper = sql.upper()
        where_idx = upper.rfind(" WHERE ")
        if where_idx < 0:
            return None
        where_part = sql[where_idx + 7:]

        # 移除可能存在的 GROUP BY / HAVING / ORDER BY / LIMIT 等后续子句
        for kw in (" GROUP BY ", " HAVING ", " ORDER BY ", " LIMIT "):
            idx = where_part.upper().find(kw)
            if idx >= 0:
                where_part = where_part[:idx]

        # 正则匹配 `field` = 'value' / "value" / 数字
        pattern = re.compile(
            r"`?(?P<field>[A-Za-z_][A-Za-z0-9_]*)`?\s*(?P<op>=|<>|!=|IN)\s*(?P<val>'[^']*'|\d+)",
            re.IGNORECASE,
        )
        for m in pattern.finditer(where_part):
            field = m.group("field")
            val_raw = m.group("val")
            val = val_raw.strip("'\"")
            op = m.group("op").upper()

            if field in owner_fields and user_id:
                real_id = str(user_id)
                # 计算可允许的 user_id 范围
                allowed_user_ids = _resolve_allowed_user_ids(user_scope, real_id, row_policies)
                # admin (None) 跳过 owner 冲突检测
                if allowed_user_ids is None:
                    continue
                if op == "IN" and val_raw.startswith("'"):
                    # IN (val1, val2, ...) 格式，需要解析列表
                    inner = val_raw.strip("'")
                    in_values = [v.strip().strip("'\"") for v in inner.split(",")]
                    if not all(v in allowed_user_ids for v in in_values if v):
                        scope_desc = _describe_scope(user_scope, real_id)
                        return {
                            "type": "FIELD_OWNER_FORBIDDEN",
                            "field": field, "operator": op, "value": val,
                            "current_user_id": real_id,
                            "message": (
                                f"权限不足：{field} IN (...) 中包含不在范围内的 user_id"
                                f"（{scope_desc}）"
                            ),
                        }
                    continue
                violation = (
                    (op in ("=", "==") and val != real_id and val not in allowed_user_ids)
                    or (op in ("!=", "<>") and val == real_id)
                )
                if violation:
                    scope_desc = _describe_scope(user_scope, real_id)
                    return {
                        "type": "FIELD_OWNER_FORBIDDEN",
                        "field": field, "operator": op, "value": val,
                        "current_user_id": real_id,
                        "message": (
                            f"权限不足：{field} 过滤值 {val} 不在您的可查询范围内"
                            f"（{scope_desc}）"
                        ),
                    }
            if field in region_fields and user_region:
                violation = (
                    (op in ("=", "==") and val != str(user_region) and val)
                    or (op in ("!=", "<>") and val == str(user_region))
                )
                if violation:
                    return {
                        "type": "FIELD_REGION_FORBIDDEN",
                        "field": field, "operator": op, "value": val,
                        "current_user_region": str(user_region),
                        "message": (
                            f"权限不足：{field} 只能过滤当前用户所在区域（{user_region}），"
                            f"不能跨区域查询"
                        ),
                    }
        return None
    except Exception as e:
        print(f"[DEBUG] _scan_sql_owner_region error: {str(e)}")
        return None


def create_authorized_sql_node():
    """创建 AUTHORIZED SQL 节点"""

    def authorized_sql_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取授权后的 SQL

        输入:
            - sql: 原始 SQL
            - authorized_sql: 授权后的 SQL

        输出:
            - sql: 使用的 SQL（优先使用 authorized_sql）
            - row_policy_applied: 行级策略是否实际追加了条件（用于方案 B 答案纠正）
        """
        authorized_sql = state.get("authorized_sql", "")
        # fallback: 如果 state 没拿到，从 permission_result 读
        if not authorized_sql:
            pr = state.get("permission_result", {}) or {}
            if isinstance(pr, dict) and pr.get("authorized_sql"):
                authorized_sql = pr.get("authorized_sql", "")
        original_sql = state.get("sql", "")
        permission_result = state.get("permission_result", {}) or {}

        # 违规场景：authorized_sql 为空时不能再回退到原始 SQL
        # 否则 sql_executor 会执行未经授权的 SQL，导致用户能拿到他人数据
        if not authorized_sql and permission_result.get("status") == "FORBIDDEN":
            print("\n========== AUTHORIZED SQL NODE OUTPUT ==========")
            print("[FORBIDDEN] SQL execution blocked by permission engine")
            print("===============================================\n")
            violations = permission_result.get("violations") or []
            err_msg = "权限不足"
            if violations:
                first = violations[0]
                if isinstance(first, dict) and first.get("message"):
                    err_msg = first["message"]
                elif isinstance(first, str):
                    err_msg = first
            return {
                "sql": "",  # 空 SQL，sql_executor 会跳过执行
                "sql_execution_blocked": True,
                "permission_block_message": err_msg,
            }

        # 如果有授权 SQL，使用授权 SQL；否则使用原 SQL
        final_sql = authorized_sql if authorized_sql else original_sql

        # 检测授权 SQL 是否相对原 SQL 多了行级策略条件
        # 用于 summarizer 判断"数据被权限收窄"，避免 LLM 误以为返回的就是用户想看的数据
        # 逻辑：当前用户存在 ROW 策略（如 sales_id=${user.id}），且授权 SQL 中含该字段过滤
        # 即视为被策略强制收窄（summarizer 决定是否需要诚实提示）
        row_policy_applied = False
        try:
            row_policies = state.get("row_policies", []) or []
            applied_fields: list = []
            for p in row_policies:
                if isinstance(p, dict) and p.get("policy_type") == "ROW" and p.get("enabled", 1):
                    cf = (p.get("condition_field") or "").strip()
                    cv = (p.get("condition_value") or "").strip()
                    if cf and ("${user.id}" in cv or "${user.region}" in cv):
                        applied_fields.append(cf)
            if applied_fields and authorized_sql:
                for f in applied_fields:
                    if re.search(rf"`?{re.escape(f)}`?\s*(=|<>|!=|IN)", authorized_sql, re.IGNORECASE):
                        # 检查原 SQL 是否也有
                        if not re.search(rf"`?{re.escape(f)}`?\s*(=|<>|!=|IN)", original_sql, re.IGNORECASE):
                            row_policy_applied = True
                            break
        except Exception:
            pass

        print("\n========== AUTHORIZED SQL NODE OUTPUT ==========")
        print(f"final_sql: {final_sql}")
        print(f"row_policy_applied: {row_policy_applied}")
        print("===============================================\n")

        return {"sql": final_sql, "row_policy_applied": row_policy_applied}

    return authorized_sql_node
