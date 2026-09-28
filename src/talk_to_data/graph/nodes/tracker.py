"""
节点追踪装饰器
"""

import time
import json
from typing import Callable, Dict, Any


def truncate_value(value: Any, max_length: int = 300) -> str:
    """截断过长的值用于记录"""
    if value is None:
        return "None"
    if isinstance(value, (str, int, float, bool)):
        s = str(value)
        return s[:max_length] + "..." if len(s) > max_length else s
    if isinstance(value, (list, dict)):
        s = json.dumps(value, ensure_ascii=False, default=str)
        return s[:max_length] + "..." if len(s) > max_length else s
    return str(type(value))


def node_tracker(node_name: str, track_input_keys: list = None, track_output_keys: list = None):
    """
    节点追踪装饰器

    Args:
        node_name: 节点名称
        track_input_keys: 要追踪的输入键列表
        track_output_keys: 要追踪的输出键列表
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
            start_time = time.time()

            # 记录输入
            if track_input_keys:
                input_data = {k: state.get(k) for k in track_input_keys if k in state}
            else:
                input_data = {"_all_keys": list(state.keys())}

            # 执行节点
            try:
                result = func(state)
                elapsed = time.time() - start_time

                # 记录结果
                if track_output_keys:
                    output_data = {k: result.get(k) for k in track_output_keys if k in result}
                else:
                    # 过滤掉元数据字段
                    meta_keys = {'node_timings', 'node_inputs', 'node_outputs'}
                    output_data = {k: v for k, v in result.items() if k not in meta_keys}

                # 使用字典合并操作更新追踪信息
                result |= {
                    "node_timings": {**result.get("node_timings", {}), node_name: elapsed},
                    "node_inputs": {**result.get("node_inputs", {}), node_name: truncate_value(input_data)},
                    "node_outputs": {**result.get("node_outputs", {}), node_name: truncate_value(output_data)},
                }

                return result

            except Exception as e:
                elapsed = time.time() - start_time
                error_result = {
                    "error": str(e),
                    "node_timings": {**state.get("node_timings", {}), node_name: elapsed},
                    "node_inputs": {**state.get("node_inputs", {}), node_name: truncate_value(input_data)},
                    "node_outputs": {**state.get("node_outputs", {}), node_name: f"ERROR: {str(e)[:100]}"},
                }
                return error_result

        return wrapper
    return decorator


def create_tracked_node(node_name: str, original_node: Callable, track_input_keys: list = None, track_output_keys: list = None) -> Callable:
    """
    创建带追踪功能的节点

    Args:
        node_name: 节点名称
        original_node: 原始节点函数
        track_input_keys: 要追踪的输入键
        track_output_keys: 要追踪的输出键
    """
    return node_tracker(node_name, track_input_keys, track_output_keys)(original_node)
