"""
用户角色获取节点
"""

import json
import os
import pymysql
from typing import Dict, Any


def create_user_roles_node():
    """创建 GET USER ROLES 节点"""

    def user_roles_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== USER ROLES NODE INPUT ==========")
        print(f"user_id: {state.get('user_id')}")
        print(f"============================================\n")

        user_id = state.get("user_id", "")
        user_roles = []

        if user_id:
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

                sql = """
                SELECT
                    r.id AS role_id,
                    r.name AS role_name
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = %s
                ORDER BY r.id
                """

                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(sql, (user_id,))
                    results = cursor.fetchall()
                    user_roles = [dict(r) for r in results]

                conn.close()
                print(f"[DEBUG] User roles fetched: {user_roles}")

            except Exception as e:
                print(f"[DEBUG] User roles error: {str(e)}")

        print(f"\n========== USER ROLES NODE OUTPUT ==========")
        print(f"user_roles: {user_roles}")
        print(f"============================================\n")

        return {"user_roles": user_roles}

    return user_roles_node
