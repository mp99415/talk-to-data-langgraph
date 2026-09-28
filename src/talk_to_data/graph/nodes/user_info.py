"""
用户信息获取节点
"""

import json
import os
import pymysql
from typing import Dict, Any


def create_user_info_node():
    """创建 GET USER INFO 节点"""

    def user_info_node(state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n========== USER INFO NODE INPUT ==========")
        print(f"user_id: {state.get('user_id')}")
        print(f"==========================================\n")

        user_id = state.get("user_id", "")
        user_info = []

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
                    u.id AS user_id,
                    u.username,
                    u.name,
                    u.department_id,
                    d.name AS department_name,
                    u.region
                FROM users u
                LEFT JOIN departments d ON d.id = u.department_id
                WHERE u.id = %s
                LIMIT 1
                """

                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(sql, (user_id,))
                    result = cursor.fetchone()
                    if result:
                        user_info = [dict(result)]

                conn.close()
                print(f"[DEBUG] User info fetched: {user_info}")

            except Exception as e:
                print(f"[DEBUG] User info error: {str(e)}")

        print(f"\n========== USER INFO NODE OUTPUT ==========")
        print(f"user_info: {user_info}")
        print(f"==========================================\n")

        return {"user_info": user_info}

    return user_info_node
