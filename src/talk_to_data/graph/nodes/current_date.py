"""
获取当前日期节点
"""

from datetime import datetime
from typing import Dict, Any


def create_get_current_date_node():
    """创建获取当前日期节点"""

    def get_current_date(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取当前日期信息

        Returns:
            包含当前日期的字典
        """
        now = datetime.now()

        return {
            "current_date": now.strftime("%Y-%m-%d"),
            "current_year": now.year,
            "current_month": now.month,
            "current_day": now.day,
            "current_datetime": now.isoformat()
        }

    return get_current_date
