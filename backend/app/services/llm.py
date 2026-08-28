import json
from typing import Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from openai import OpenAI

from app.config import get_settings

def get_llm(model: Optional[str] = None, temperature: float = 0.7) -> ChatOpenAI:
    """获取标准通用 LLM 实例（默认 qwen3.7-plus）"""
    settings = get_settings()
    return ChatOpenAI(
        model=model or settings.model_text_plus,
        api_key=settings.model_router_api_key,
        base_url=settings.model_router_base_url,
        temperature=temperature,
    )

def get_flagship_llm(temperature: float = 0.3) -> ChatOpenAI:
    """获取深度分析/推理旗舰模型（qwen3.8-max）"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_text_flagship,
        api_key=settings.model_router_api_key,
        base_url=settings.model_router_base_url,
        temperature=temperature,
    )

def get_fast_llm(temperature: float = 0.2) -> ChatOpenAI:
    """获取快速校验/短文本模型（qwen3.6-flash）"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_text_flash,
        api_key=settings.model_router_api_key,
        base_url=settings.model_router_base_url,
        temperature=temperature,
    )

def get_raw_openai_client() -> OpenAI:
    """获取底层 OpenAI 客户端实例"""
    settings = get_settings()
    return OpenAI(
        api_key=settings.model_router_api_key,
        base_url=settings.model_router_base_url,
    )
