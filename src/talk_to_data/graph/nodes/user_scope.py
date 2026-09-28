"""
User Scope Calculator 节点
根据当前用户的角色，计算可查询的 user_id 范围（user_scope）。

user_scope 格式:
{
    "scope_type": "self" | "team" | "department" | "all",
    "allowed_user_ids": ["1001", "1002", ...],
}

设计思路:
- 销售 (role=3, sales): scope_type=self
- 销售总监 (role=4, sales_director): scope_type=department, allowed=本部门所有 sales_id
- 管理员 (admin): scope_type=all

当前实现:
- 从 user_info 读取 department_id
- 从 users 表查询同部门的其他销售
- 形成 allowed_user_ids

未来演进:
- 从 user_query_scopes 表（待设计）读取更精细的 scope 配置
- 支持 region 维度的 scope
- 支持跨部门授权
"""

import os
import pymysql
from typing import Dict, Any, List, Optional


# 角色 → scope_type 映射
# 当前是基于 role_name 的简单映射，未来可改为基于 user_query_scopes 表
_ROLE_SCOPE_TYPE = {
    "admin": "all",
    "super_admin": "all",
    "sales_director": "department",
    "sales_manager": "department",
    "team_lead": "team",
    "sales": "self",
    "default": "self",
}


def _get_db_connection():
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com")
    db_port = int(os.getenv("DB_PORT", "63888"))
    db_name = os.getenv("DB_NAME", "talktodata")
    return pymysql.connect(
        host=db_host,
        port=db_port,
        user="root",
        password=db_password,
        database=db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _query_department_user_ids(
    department_id: Optional[int],
    exclude_self: bool = False,
    current_user_id: Optional[str] = None,
) -> List[str]:
    """查询同一部门的所有 user_id（不包括 admin 等跨部门用户）"""
    if not department_id:
        return []
    try:
        conn = _get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT id FROM users
                WHERE department_id = %s AND status = 'ACTIVE'
            """
            params = [department_id]
            if exclude_self and current_user_id:
                sql += " AND id != %s"
                params.append(current_user_id)
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        conn.close()
        return [str(r["id"]) for r in rows]
    except Exception as e:
        print(f"[DEBUG] _query_department_user_ids error: {str(e)}")
        return []


def _query_team_user_ids(current_user_id: str) -> List[str]:
    """
    查询当前用户所在团队（manager_id = current_user_id）的所有 user_id
    用于 team_lead 角色
    """
    try:
        conn = _get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT id FROM users
                WHERE manager_id = %s AND status = 'ACTIVE'
            """
            cursor.execute(sql, (current_user_id,))
            rows = cursor.fetchall()
        conn.close()
        return [str(r["id"]) for r in rows] + [str(current_user_id)]
    except Exception as e:
        print(f"[DEBUG] _query_team_user_ids error: {str(e)}")
        return [str(current_user_id)]


def compute_user_scope(
    user_info: Dict[str, Any],
    user_roles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    根据用户信息和角色，计算可查询的 user_id 范围。

    返回 user_scope:
      - {"scope_type": "all"}                      # 全部
      - {"scope_type": "self", "allowed_user_ids": ["1001"]}
      - {"scope_type": "department", "allowed_user_ids": [...]}
      - {"scope_type": "team", "allowed_user_ids": [...]}
    """
    current_user_id = str(user_info.get("user_id") or "")
    department_id = user_info.get("department_id")

    # 取角色中优先级最高的 scope_type
    scope_type = "self"
    role_names = [r.get("role_name", "") for r in (user_roles or [])]

    # 优先级：admin > sales_director > sales_manager > team_lead > sales
    for rn in role_names:
        rt = _ROLE_SCOPE_TYPE.get(rn, _ROLE_SCOPE_TYPE["default"])
        if rt == "all":
            scope_type = "all"
            break
        elif rt == "department" and scope_type not in ("all", "department"):
            scope_type = "department"
        elif rt == "team" and scope_type not in ("all", "department", "team"):
            scope_type = "team"

    # 计算 allowed_user_ids
    if scope_type == "all":
        return {
            "scope_type": "all",
            "allowed_user_ids": None,  # None 表示不限制
        }
    elif scope_type == "self":
        return {
            "scope_type": "self",
            "allowed_user_ids": [current_user_id],
        }
    elif scope_type == "department":
        allowed = _query_department_user_ids(department_id, current_user_id=current_user_id)
        if current_user_id not in allowed:
            allowed.append(current_user_id)
        return {
            "scope_type": "department",
            "allowed_user_ids": allowed,
        }
    elif scope_type == "team":
        allowed = _query_team_user_ids(current_user_id)
        return {
            "scope_type": "team",
            "allowed_user_ids": allowed,
        }

    # fallback
    return {
        "scope_type": "self",
        "allowed_user_ids": [current_user_id],
    }


def create_user_scope_node():
    """创建 USER SCOPE 节点"""

    def user_scope_node(state: Dict[str, Any]) -> Dict[str, Any]:
        user_info = state.get("user_info", [])
        user_roles = state.get("user_roles", [])
        row_policies = state.get("row_policies", [])

        # DB 不可达时（user_info 为空），返回 None 让 permission_engine 走降级逻辑：
        # 如果 row_policies 也为空，降级为 all（无限制），允许查他人
        if not user_info:
            print("[DEBUG] user_scope: user_info 为空（DB 不可达？），返回 None 让 permission_engine 降级处理")
            return {"user_scope": None}

        # 有 user_roles 但没 row_policies，也降级为 None
        if not row_policies:
            return {"user_scope": None}

        current_user = user_info[0] if isinstance(user_info, list) else user_info
        scope = compute_user_scope(current_user, user_roles)

        print(f"[INFO] user_scope 计算: user_id={current_user.get('user_id')} "
              f"scope_type={scope.get('scope_type')} "
              f"allowed_count={len(scope.get('allowed_user_ids') or [])}")
        return {"user_scope": scope}

    return user_scope_node