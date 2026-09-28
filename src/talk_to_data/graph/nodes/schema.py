"""
Schema 相关节点
"""

import json
import os
import time
import pymysql
from typing import Dict, Any


def create_schema_builder_node():
    """创建 SCHEMA BUILDER 节点"""

    def schema_builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        print(f"\n========== SCHEMA BUILDER NODE INPUT ==========")
        print(f"state keys: {list(state.keys())}")
        
        db_host = os.getenv("DB_HOST", "gz-cdb-gjap36mn.sql.tencentcdb.com")
        db_name = os.getenv("DB_NAME", "talktodata")
        db_password = os.getenv("DB_PASSWORD")
        db_port = int(os.getenv("DB_PORT", "63888"))

        print(f"[DEBUG] DB config: host={db_host}, port={db_port}, db={db_name}")
        
        # 直接使用 pymysql 连接数据库
        try:
            conn = pymysql.connect(
                host=db_host,
                port=db_port,
                user="root",
                password=db_password,
                database=db_name,
                charset="utf8mb4"
            )
            
            # 获取表结构
            columns_sql = """
            SELECT 
                TABLE_NAME,
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_KEY,
                COLUMN_COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(columns_sql, (db_name,))
                columns = cursor.fetchall()
                print(f"[DEBUG] Got {len(columns)} columns")
                
            # 获取外键
            fks_sql = """
            SELECT 
                TABLE_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME,
                CONSTRAINT_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
            AND REFERENCED_TABLE_NAME IS NOT NULL
            """
            
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(fks_sql, (db_name,))
                foreign_keys = cursor.fetchall()
                print(f"[DEBUG] Got {len(foreign_keys)} foreign keys")

            # 构建 columns 格式
            columns_dict = {}
            for col in columns:
                table = col['TABLE_NAME']
                if table not in columns_dict:
                    columns_dict[table] = []
                columns_dict[table].append({
                    "name": col['COLUMN_NAME'],
                    "type": col['DATA_TYPE'],
                    "nullable": col['IS_NULLABLE'] == 'YES',
                    "key": col['COLUMN_KEY'],
                    "comment": col['COLUMN_COMMENT']
                })
            
            columns_result = columns_dict
            fks_result = foreign_keys
            
            # 获取业务元数据表
            metadata_result = {}
            try:
                # 查询 semantic_dimensions 表
                dims_sql = "SELECT * FROM semantic_dimensions"
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(dims_sql)
                    dims = cursor.fetchall()
                    metadata_result["semantic_dimensions"] = [dict(d) for d in dims]
                    print(f"[DEBUG] Got {len(dims)} semantic dimensions")

                # 查询 semantic_dimension_values 表
                vals_sql = "SELECT * FROM semantic_dimension_values"
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(vals_sql)
                    vals = cursor.fetchall()
                    metadata_result["semantic_dimension_values"] = [dict(v) for v in vals]
                    print(f"[DEBUG] Got {len(vals)} semantic dimension values")

                # 查询 semantic_value_aliases 表
                aliases_sql = "SELECT * FROM semantic_value_aliases"
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(aliases_sql)
                    aliases = cursor.fetchall()
                    metadata_result["semantic_value_aliases"] = [dict(a) for a in aliases]
                    print(f"[DEBUG] Got {len(aliases)} semantic value aliases")

                # 查询 data_fields 表
                fields_sql = "SELECT * FROM data_fields"
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(fields_sql)
                    fields = cursor.fetchall()
                    metadata_result["data_fields"] = [dict(f) for f in fields]
                    print(f"[DEBUG] Got {len(fields)} data fields")

            except Exception as e:
                print(f"[DEBUG] Metadata query error: {str(e)}")
                metadata_result = {"error": str(e)}

            # 尝试读取 column_metadata 表（用于配置驱动的用户引用）
            column_metadata_rows = []
            try:
                meta_sql = """
                SELECT table_name, column_name, user_reference,
                       user_reference_type, user_reference_label
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'column_metadata'
                LIMIT 1
                """
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(meta_sql, (db_name,))
                    exists = cursor.fetchone()
                if exists:
                    cm_sql = """
                    SELECT table_name, column_name, user_reference,
                           user_reference_type, user_reference_label
                    FROM column_metadata
                    """
                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute(cm_sql)
                        column_metadata_rows = cursor.fetchall()
                    print(f"[DEBUG] Got {len(column_metadata_rows)} column_metadata rows")
            except Exception as e:
                print(f"[DEBUG] column_metadata query skipped: {str(e)}")

            finally:
                conn.close()

        except Exception as e:
            print(f"[DEBUG] Database error: {str(e)}")
            columns_result = {"error": str(e)}
            fks_result = {"error": str(e)}
            metadata_result = {"error": str(e)}

        schema = {
            "columns": columns_result,
            "foreign_keys": fks_result,
            "metadata": metadata_result,
            "column_metadata": [dict(r) for r in column_metadata_rows],
        }

        # 解析用户引用字段配置（合并多种数据源）
        try:
            from talk_to_data.config.user_reference_config import (
                parse_user_reference_from_schema, get_default_config,
            )
            user_ref_fields = parse_user_reference_from_schema(
                schema, get_default_config()
            )
            schema["user_reference_fields"] = user_ref_fields
            print(f"[DEBUG] Resolved {len(user_ref_fields)} user_reference fields")
        except Exception as e:
            print(f"[DEBUG] parse_user_reference_from_schema error: {str(e)}")
            schema["user_reference_fields"] = {}

        elapsed = time.time() - start_time

        print(f"========== SCHEMA BUILDER NODE OUTPUT ==========")
        tables = list(columns_result.keys()) if isinstance(columns_result, dict) else []
        print(f"schema tables: {tables}")
        print(f"metadata keys: {list(metadata_result.keys())}")
        print(f"[TIMER] Schema Builder: {elapsed:.2f}s")
        print(f"===============================================\n")

        return {"schema": schema, "node_timings": {"schema_builder": elapsed}}

    return schema_builder_node
