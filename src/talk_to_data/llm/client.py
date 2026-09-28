"""
LLM 客户端配置
"""

import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

_llm_instance: Optional[BaseChatModel] = None


def get_llm(
    model: str = None,
    temperature: float = None,
    base_url: str = None,
    api_key: str = None
) -> BaseChatModel:
    """
    获取 LLM 客户端单例
    
    Args:
        model: 模型名称，默认从环境变量 LLM_MODEL 获取
        temperature: 温度参数，默认从环境变量 LLM_TEMPERATURE 获取
        base_url: API 基础 URL
        api_key: API Key
    
    Returns:
        LLM 客户端
    """
    global _llm_instance
    
    if _llm_instance is not None:
        return _llm_instance
    
    model = model or os.getenv("LLM_MODEL", "qwen3.6-flash")
    temperature = temperature if temperature is not None else float(os.getenv("LLM_TEMPERATURE", "0"))
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    
    _llm_instance = ChatOpenAI(
        model=model,
        temperature=temperature,
        base_url=base_url,
        api_key=api_key
    )
    
    return _llm_instance


def reset_llm():
    """重置 LLM 实例"""
    global _llm_instance
    _llm_instance = None
