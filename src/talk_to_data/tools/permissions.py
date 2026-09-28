"""
权限工具
"""

import json
from typing import Dict, Any, List
from langchain_core.tools import tool


@tool("get_user_info")
def get_user_info_tool(user_id: str) -> str:
    """
    获取用户信息
    
    Args:
        user_id: 用户 ID
    
    Returns:
        用户信息（JSON 字符串）
    """
    user_info = {
        "user_id": user_id,
        "name": "User",
        "department": "Default Department"
    }
    
    return json.dumps(user_info, ensure_ascii=False)


@tool("get_user_roles")
def get_user_roles_tool(user_id: str) -> str:
    """
    获取用户角色
    
    Args:
        user_id: 用户 ID
    
    Returns:
        角色列表（JSON 字符串）
    """
    roles = ["user"]
    
    return json.dumps({"roles": roles}, ensure_ascii=False)


@tool("get_rbac_permissions")
def get_rbac_permissions_tool(roles: List[str]) -> str:
    """
    获取 RBAC 权限
    
    Args:
        roles: 角色列表
    
    Returns:
        权限信息（JSON 字符串）
    """
    permissions = {
        "tables": ["customers", "orders", "products"],
        "fields": ["*"],
        "row_policy": None
    }
    
    return json.dumps(permissions, ensure_ascii=False)
