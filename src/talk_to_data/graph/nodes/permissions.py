"""
权限查询节点 - 获取 RBAC 权限、字段权限、行级策略
"""

import json
import os
import pymysql
from typing import Dict, Any


def create_rbac_permissions_node():
    """创建 GET RBAC PERMISSIONS 节点"""

    def rbac_permissions_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== RBAC PERMISSIONS NODE INPUT ==========")
        print(f"user_roles: {state.get('user_roles', [])}")
        print(f"==================================================\n")

        user_roles = state.get("user_roles", [])
        role_permissions = []

        if user_roles:
            try:
                db_host = os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com")
                db_name = os.getenv("DB_NAME", "talktodata")
                db_port = int(os.getenv("DB_PORT", "63888"))
                db_password = os.getenv("DB_PASSWORD")

                conn = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    user="root",
                    password=db_password,
                    database=db_name,
                    charset="utf8mb4"
                )

                role_ids = [r.get("role_id") for r in user_roles if r.get("role_id")]
                if role_ids:
                    placeholders = ",".join(["%s"] * len(role_ids))
                    # role_permissions 是关联表，需要 JOIN permissions 表获取详情
                    sql = f"""
                    SELECT
                        p.id AS permission_id,
                        rp.role_id,
                        p.code,
                        p.name,
                        p.resource,
                        p.action,
                        p.effect
                    FROM role_permissions rp
                    JOIN permissions p ON rp.permission_id = p.id
                    WHERE rp.role_id IN ({placeholders})
                    ORDER BY rp.role_id, p.id
                    """

                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute(sql, tuple(role_ids))
                        results = cursor.fetchall()
                        role_permissions = [dict(r) for r in results]

                conn.close()
                print(f"[DEBUG] RBAC permissions fetched: {len(role_permissions)} records")

            except Exception as e:
                print(f"[DEBUG] RBAC permissions error: {str(e)}")

        print(f"\n========== RBAC PERMISSIONS NODE OUTPUT ==========")
        print(f"role_permissions: {role_permissions[:3]}...")  # 只打印前3条
        print(f"==================================================\n")

        return {"role_permissions": role_permissions}

    return rbac_permissions_node


def create_field_permissions_node():
    """创建 GET FIELD PERMISSIONS 节点"""

    def field_permissions_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== FIELD PERMISSIONS NODE INPUT ==========")
        print(f"user_roles: {state.get('user_roles', [])}")
        print(f"==================================================\n")

        user_roles = state.get("user_roles", [])
        field_permissions = []

        if user_roles:
            try:
                db_host = os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com")
                db_name = os.getenv("DB_NAME", "talktodata")
                db_port = int(os.getenv("DB_PORT", "63888"))
                db_password = os.getenv("DB_PASSWORD")

                conn = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    user="root",
                    password=db_password,
                    database=db_name,
                    charset="utf8mb4"
                )

                role_ids = [r.get("role_id") for r in user_roles if r.get("role_id")]
                if role_ids:
                    placeholders = ",".join(["%s"] * len(role_ids))
                    # 使用 role_field_permissions 表，需要 JOIN data_fields 和 data_resources 获取字段信息
                    sql = f"""
                    SELECT
                        rfp.role_id,
                        dr.table_name,
                        df.field_name,
                        df.business_name,
                        rfp.can_read,
                        rfp.can_export
                    FROM role_field_permissions rfp
                    JOIN data_fields df ON rfp.field_id = df.id
                    JOIN data_resources dr ON df.resource_id = dr.id
                    WHERE rfp.role_id IN ({placeholders})
                    ORDER BY rfp.role_id, dr.table_name, df.field_name
                    """

                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute(sql, tuple(role_ids))
                        results = cursor.fetchall()
                        field_permissions = [dict(r) for r in results]

                conn.close()
                print(f"[DEBUG] Field permissions fetched: {len(field_permissions)} records")

            except Exception as e:
                print(f"[DEBUG] Field permissions error: {str(e)}")

        print(f"\n========== FIELD PERMISSIONS NODE OUTPUT ==========")
        print(f"field_permissions: {field_permissions[:3]}...")
        print(f"==================================================\n")

        return {"field_permissions": field_permissions}

    return field_permissions_node


def create_row_policies_node():
    """创建 GET ROW POLICIES 节点"""

    def row_policies_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== ROW POLICIES NODE INPUT ==========")
        print(f"user_roles: {state.get('user_roles', [])}")
        print(f"==============================================\n")

        user_roles = state.get("user_roles", [])
        row_policies = []

        if user_roles:
            try:
                db_host = os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com")
                db_name = os.getenv("DB_NAME", "talktodata")
                db_port = int(os.getenv("DB_PORT", "63888"))
                db_password = os.getenv("DB_PASSWORD")

                conn = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    user="root",
                    password=db_password,
                    database=db_name,
                    charset="utf8mb4"
                )

                role_ids = [r.get("role_id") for r in user_roles if r.get("role_id")]
                if role_ids:
                    placeholders = ",".join(["%s"] * len(role_ids))
                    # 使用 data_policies 表
                    sql = f"""
                    SELECT
                        dp.id AS row_policy_id,
                        dp.role_id,
                        dp.policy_name,
                        dp.policy_type,
                        dp.condition_field,
                        dp.condition_operator,
                        dp.condition_value,
                        dp.enabled
                    FROM data_policies dp
                    WHERE dp.role_id IN ({placeholders}) AND dp.enabled = 1
                    ORDER BY dp.role_id, dp.id
                    """

                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute(sql, tuple(role_ids))
                        results = cursor.fetchall()
                        row_policies = [dict(r) for r in results]

                conn.close()
                print(f"[DEBUG] Row policies fetched: {len(row_policies)} records")

            except Exception as e:
                print(f"[DEBUG] Row policies error: {str(e)}")

        print(f"\n========== ROW POLICIES NODE OUTPUT ==========")
        print(f"row_policies: {row_policies[:3]}...")
        print(f"==============================================\n")

        return {"row_policies": row_policies}

    return row_policies_node
