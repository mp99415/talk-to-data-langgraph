"""
权限解析器节点
"""

import json
from typing import Dict, Any, List, Optional


# =========================================================
# 1. 基础解析
# =========================================================
def parse_value(value: Any) -> Any:
    """解析各种格式的值"""
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str):
        return value

    value = value.strip()

    if not value:
        return None

    try:
        return json.loads(value)
    except Exception:
        pass

    lines = [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]

    if len(lines) >= 2 and "|" in lines[0]:
        headers = [
            x.strip()
            for x in lines[0].strip("|").split("|")
        ]

        rows = []

        for line in lines[1:]:
            if "|" not in line:
                continue

            values = [
                x.strip()
                for x in line.strip("|").split("|")
            ]

            if len(values) != len(headers):
                continue

            if all(
                not x or set(x) <= {"-"}
                for x in values
            ):
                continue

            rows.append(
                dict(zip(headers, values))
            )

        return rows

    return value


# =========================================================
# 2. DB Query records 解包
# =========================================================
def extract_records(value: Any) -> List[Dict]:
    """提取记录"""
    value = parse_value(value)

    if value is None:
        return []

    if isinstance(value, dict):
        if "records" in value:
            records = value.get("records")
            if isinstance(records, list):
                return records
            if isinstance(records, dict):
                return [records]
        return [value]

    if isinstance(value, list):
        result = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if "records" in item:
                records = item.get("records")
                if isinstance(records, list):
                    result.extend(records)
                elif isinstance(records, dict):
                    result.append(records)
            else:
                result.append(item)
        return result

    return []


# =========================================================
# 3. Boolean
# =========================================================
def to_bool(value: Any) -> Optional[bool]:
    """转换为布尔值"""
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return bool(value)

    value = str(value).strip().lower()

    if value in [
        "true",
        "1",
        "yes",
        "y",
        "allow",
        "allowed"
    ]:
        return True

    if value in [
        "false",
        "0",
        "no",
        "n",
        "deny",
        "denied"
    ]:
        return False

    return None


# =========================================================
# 4. Effect
# =========================================================
def normalize_effect(value: Any) -> Optional[str]:
    """标准化权限效果"""
    if value is None:
        return None

    value = str(value).strip().upper()

    if value in [
        "ALLOW",
        "PERMIT",
        "GRANT"
    ]:
        return "ALLOW"

    if value in [
        "DENY",
        "REJECT",
        "FORBID"
    ]:
        return "DENY"

    return None


def resolve_effect(effects: List) -> tuple:
    """解析权限效果列表"""
    has_allow = False
    has_deny = False

    for effect in effects:
        effect = normalize_effect(effect)

        if effect == "DENY":
            has_deny = True

        elif effect == "ALLOW":
            has_allow = True

    if has_deny:
        return False, "DENY"

    if has_allow:
        return True, "ALLOW"

    return False, "NONE"


# =========================================================
# 5. Policy Value
# =========================================================
def normalize_policy_value(value: Any) -> Dict:
    """标准化策略值"""
    if value is None:
        return {
            "type": "LITERAL",
            "value": None
        }

    if isinstance(value, dict):
        return value

    value = str(value).strip()

    if value == "${user.id}":
        return {
            "type": "USER_ATTRIBUTE",
            "attribute": "id"
        }

    if value == "${user.region}":
        return {
            "type": "USER_ATTRIBUTE",
            "attribute": "region"
        }

    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    return {
        "type": "LITERAL",
        "value": value
    }


# =========================================================
# 权限解析器主逻辑
# =========================================================
def create_permission_resolver_node():
    """创建权限解析器节点"""

    def permission_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== PERMISSION RESOLVER NODE INPUT ==========")

        errors: List[str] = []

        raw_authorization = {
            "user": state.get("user_info"),
            "roles": state.get("user_roles"),
            "role_permissions": state.get("role_permissions"),
            "field_permissions": state.get("field_permissions"),
            "row_policies": state.get("row_policies")
        }

        print(f"user_info: {raw_authorization.get('user')}")
        print(f"user_roles: {raw_authorization.get('roles')}")
        role_perms = raw_authorization.get('role_permissions') or []
        field_perms = raw_authorization.get('field_permissions') or []
        row_pol = raw_authorization.get('row_policies') or []
        print(f"role_permissions count: {len(role_perms)}")
        print(f"field_permissions count: {len(field_perms)}")
        print(f"row_policies count: {len(row_pol)}")
        print(f"====================================================\n")

        # 直接使用原始数据，不经过 parse_value 转换
        # parse_value 会破坏原始数据结构

        if not isinstance(raw_authorization, dict):
            return {
                "effective_permission": {
                    "version": 1,
                    "status": "ERROR",
                    "user": {},
                    "roles": [],
                    "tables": {},
                    "fields": {},
                    "row_policies": []
                },
                "status": "ERROR",
                "errors": [
                    "raw_authorization is not a valid object"
                ]
            }

        # =====================================================
        # 7. Extract - 直接使用原始数据
        # =====================================================
        # 提取用户信息
        user_records = raw_authorization.get("user") or []

        # 提取角色信息
        role_records = raw_authorization.get("roles") or []

        # 提取角色权限
        role_permissions = raw_authorization.get("role_permissions") or []

        # 提取字段权限
        field_permissions = raw_authorization.get("field_permissions") or []

        # 提取行级策略
        row_policies = raw_authorization.get("row_policies") or []

        # =====================================================
        # 8. User
        # =====================================================
        if user_records:
            raw_user = user_records[0]
        else:
            raw_user = {}
            errors.append(
                "user records are empty"
            )

        user = {
            "user_id": raw_user.get("user_id"),
            "username": raw_user.get("username"),
            "name": raw_user.get("name"),
            "department_id": raw_user.get("department_id"),
            "department_name": raw_user.get("department_name"),
            "region": raw_user.get("region")
        }

        if user["user_id"] is None:
            errors.append(
                "user_id is missing"
            )

        # =====================================================
        # 9. Roles
        # =====================================================
        roles = []
        role_seen = set()
        current_role_ids = set()

        for item in role_records:
            if not isinstance(item, dict):
                continue

            role_id = item.get("role_id")
            role_name = item.get("role_name")

            if (
                role_id is None
                and role_name is None
            ):
                continue

            key = (
                str(role_id),
                str(role_name)
            )

            if key in role_seen:
                continue

            role_seen.add(key)

            roles.append({
                "role_id": role_id,
                "role_name": role_name
            })

            if role_id is not None:
                current_role_ids.add(
                    str(role_id)
                )

        # =====================================================
        # 10. Table Permission
        # =====================================================
        table_effects = {}

        for item in role_permissions:
            if not isinstance(item, dict):
                continue

            resource = (
                item.get("resource")
                or item.get("permission_resource")
            )

            action = (
                item.get("action")
                or item.get("permission_action")
            )

            effect = normalize_effect(
                item.get("effect")
                or item.get("permission_effect")
            )

            if not resource or not action:
                continue

            resource = str(resource).strip()
            action = str(action).strip().lower()

            if resource not in table_effects:
                table_effects[resource] = {
                    "read": [],
                    "export": []
                }

            if effect is not None:
                if action == "read":
                    table_effects[resource]["read"].append(effect)
                elif action == "export":
                    table_effects[resource]["export"].append(effect)
            else:
                if action == "read":
                    table_effects[resource]["read"].append("ALLOW")
                elif action == "export":
                    table_effects[resource]["export"].append("ALLOW")

        tables = {}

        for table, actions in table_effects.items():
            read, read_effect = resolve_effect(
                actions["read"]
            )
            export, export_effect = resolve_effect(
                actions["export"]
            )

            tables[table] = {
                "read": read,
                "export": export,
                "read_effect": read_effect,
                "export_effect": export_effect
            }

        # =====================================================
        # 11. Field Permission
        # =====================================================
        field_effects = {}

        for item in field_permissions:
            if not isinstance(item, dict):
                continue

            table = item.get("table_name")
            field = item.get("field_name")

            if not table or not field:
                continue

            table = str(table).strip()
            field = str(field).strip()

            key = f"{table}.{field}"

            if key not in field_effects:
                field_effects[key] = {
                    "read": [],
                    "export": []
                }

            effect = normalize_effect(
                item.get("effect")
                or item.get("field_effect")
            )

            can_read = to_bool(
                item.get("can_read")
                if item.get("can_read") is not None
                else item.get("field_can_read")
            )

            can_export = to_bool(
                item.get("can_export")
                if item.get("can_export") is not None
                else item.get("field_can_export")
            )

            if effect is not None:
                if can_read is True:
                    field_effects[key]["read"].append(effect)
                if can_export is True:
                    field_effects[key]["export"].append(effect)
            else:
                if can_read is True:
                    field_effects[key]["read"].append("ALLOW")
                if can_export is True:
                    field_effects[key]["export"].append("ALLOW")

        fields = {}

        for key, actions in field_effects.items():
            table, field = key.split(".", 1)

            read, read_effect = resolve_effect(
                actions["read"]
            )
            export, export_effect = resolve_effect(
                actions["export"]
            )

            fields[key] = {
                "table": table,
                "field": field,
                "read": read,
                "export": export,
                "read_effect": read_effect,
                "export_effect": export_effect
            }

        # =====================================================
        # 12. Table → Field 上限
        # =====================================================
        for key, field in fields.items():
            table_name = field["table"]

            table_permission = tables.get(
                table_name
            )

            if table_permission is None:
                field["read"] = False
                field["export"] = False
                field["read_effect"] = "NONE"
                field["export_effect"] = "NONE"
                continue

            if not table_permission["read"]:
                field["read"] = False
                if table_permission["read_effect"] == "DENY":
                    field["read_effect"] = "DENY"
                else:
                    field["read_effect"] = "NONE"

            if not table_permission["export"]:
                field["export"] = False
                if table_permission["export_effect"] == "DENY":
                    field["export_effect"] = "DENY"
                else:
                    field["export_effect"] = "NONE"

        # =====================================================
        # 13. Row Policy
        # =====================================================
        row_policies = []
        policy_seen = set()

        for item in row_policies:
            if not isinstance(item, dict):
                continue

            policy_role_id = item.get("role_id")

            table = (
                item.get("table_name")
                or item.get("policy_table")
                or item.get("table")
            )

            condition_field = item.get("condition_field")

            condition_operator = item.get("condition_operator")

            condition_value = item.get("condition_value")

            policy_type = (
                item.get("policy_type")
                or "ROW"
            )

            effect = normalize_effect(
                item.get("effect")
                or item.get("policy_effect")
            )

            if not table:
                continue

            if not condition_field:
                continue

            if not condition_operator:
                continue

            # 角色过滤
            if (
                policy_role_id is not None
                and str(policy_role_id)
                not in current_role_ids
            ):
                continue

            # 只处理 ROW Policy
            if str(policy_type).upper() != "ROW":
                continue

            # 去重
            key = (
                str(table),
                str(condition_field),
                str(condition_operator),
                str(condition_value),
                str(policy_role_id),
                str(effect)
            )

            if key in policy_seen:
                continue

            policy_seen.add(key)

            row_policies.append({
                "table": str(table),
                "policy_id": item.get("policy_id"),
                "role_id": policy_role_id,
                "policy_type": "ROW",
                "effect": effect,
                "condition": {
                    "field": str(condition_field),
                    "operator": str(condition_operator),
                    "value": normalize_policy_value(condition_value)
                }
            })

        # =====================================================
        # 14. Effective Permission
        # =====================================================
        effective_permission = {
            "version": 1,
            "status": (
                "ERROR"
                if errors
                else "OK"
            ),
            "user": user,
            "roles": roles,
            "tables": tables,
            "fields": fields,
            "row_policies": row_policies
        }

        # =====================================================
        # 15. Return
        # =====================================================
        return {
            "effective_permission": effective_permission,
            "status": (
                "ERROR"
                if errors
                else "OK"
            ),
            "errors": errors
        }

    return permission_resolver_node
