"""
数据库工具
"""

import os
import json
from typing import Dict, Any, List
from langchain_core.tools import tool


@tool("sql_query")
def sql_query_tool(
    db_host: str,
    db_name: str,
    db_port: int,
    sql: str,
    db_password: str = None
) -> str:
    """
    执行 SQL 查询工具
    
    Args:
        db_host: 数据库主机
        db_name: 数据库名称
        db_port: 数据库端口
        sql: SQL 语句
        db_password: 数据库密码
    
    Returns:
        查询结果（JSON 字符串）
    """
    db_password = db_password or os.getenv("DB_PASSWORD")
    
    try:
        import pymysql
        
        connection = pymysql.connect(
            host=db_host,
            port=db_port,
            user="root",
            password=db_password,
            database=db_name,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with connection.cursor() as cursor:
            cursor.execute(sql)
            result = cursor.fetchall()
            connection.close()
            
            return json.dumps(result, ensure_ascii=False, default=str)
    
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool("get_physical_columns")
def get_physical_columns_tool(
    db_host: str,
    db_name: str,
    db_password: str = None,
    db_port: int = None
) -> str:
    """获取数据库物理字段"""
    db_password = db_password or os.getenv("DB_PASSWORD")
    db_port = db_port or int(os.getenv("DB_PORT", "63888"))
    
    sql = f"""
    SELECT 
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        COLUMN_KEY,
        COLUMN_COMMENT
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = '{db_name}'
    ORDER BY TABLE_NAME, ORDINAL_POSITION
    """
    
    return sql_query_tool(
        db_host=db_host,
        db_name=db_name,
        db_port=db_port,
        sql=sql,
        db_password=db_password
    )


# 导出底层函数供直接调用
def get_physical_foreign_keys_func(db_host: str, db_name: str, db_password: str = None, db_port: int = None) -> str:
    """获取数据库外键（底层函数）"""
    db_port = db_port or int(os.getenv("DB_PORT", "63888"))
    return get_physical_foreign_keys_tool(db_host=db_host, db_name=db_name, db_password=db_password, db_port=db_port)


# 导出底层函数供直接调用
def get_physical_columns_func(db_host: str, db_name: str, db_password: str = None, db_port: int = None) -> str:
    """获取数据库物理字段（底层函数）"""
    db_port = db_port or int(os.getenv("DB_PORT", "63888"))
    return get_physical_columns_tool(db_host=db_host, db_name=db_name, db_password=db_password, db_port=db_port)


@tool("get_physical_foreign_keys")
def get_physical_foreign_keys_tool(
    db_host: str,
    db_name: str,
    db_password: str = None,
    db_port: int = None
) -> str:
    """获取数据库外键"""
    db_password = db_password or os.getenv("DB_PASSWORD")
    db_port = db_port or int(os.getenv("DB_PORT", "63888"))
    
    sql = f"""
    SELECT 
        TABLE_NAME,
        COLUMN_NAME,
        REFERENCED_TABLE_NAME,
        REFERENCED_COLUMN_NAME,
        CONSTRAINT_NAME
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = '{db_name}'
    AND REFERENCED_TABLE_NAME IS NOT NULL
    """
    
    return sql_query_tool(
        db_host=db_host,
        db_name=db_name,
        db_port=db_port,
        sql=sql,
        db_password=db_password
    )
