"""大模型网关（阶段六 · 步骤 3-1 依赖）。

    LLMClient.is_available()   是否配置了模型（有 API Key）
    LLMClient.chat(prompt)     单轮对话，超时/失败返回 None（调用方降级）
    LLMClient.chat_json()      要求模型输出 JSON，自动抽取首个 JSON 对象

统一 30 秒超时；任何异常都被捕获并转为 None，保证"模型不可用不影响主流程"。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

DEFAULT_TIMEOUT = 30


@dataclass
class LLMCall:
    """一次模型调用的结果（便于审计与可观测）。"""

    text: str | None
    model: str
    latency_ms: float
    error: str = ""
    fallback: bool = False


class LLMClient:
    """OpenAI 兼容协议的轻量网关。"""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        settings = get_settings()
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key or ""
        self.model = settings.llm_model
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        """是否配置了可用的模型凭据。"""
        return bool(self.api_key.strip())

    def chat(self, prompt: str, system: str | None = None) -> LLMCall:
        """调用模型；未配置或失败时返回 fallback 结果（text=None）。"""
        if not self.is_available:
            return LLMCall(text=None, model=self.model, latency_ms=0.0, error="未配置 LLM_API_KEY", fallback=True)

        started = time.perf_counter()
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=self.model, messages=messages, temperature=0, timeout=self.timeout
            )
            text = (response.choices[0].message.content or "").strip()
            return LLMCall(
                text=text or None,
                model=self.model,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:  # noqa: BLE001 - 模型失败一律降级
            return LLMCall(
                text=None,
                model=self.model,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error=f"{type(exc).__name__}: {exc}",
                fallback=True,
            )

    def chat_json(self, prompt: str, system: str | None = None) -> tuple[dict[str, Any] | None, LLMCall]:
        """调用模型并要求 JSON 输出，返回 (解析后的对象, 调用信息)。"""
        call = self.chat(prompt, system)
        if not call.text:
            return None, call
        return extract_json(call.text), call


def extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出中抽取首个 JSON 对象（容忍 ```json 代码块与前后缀说明）。"""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        payload = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


@lru_cache(maxsize=1)
def get_client() -> LLMClient:
    """获取模型网关单例。"""
    return LLMClient()


def reset_client_cache() -> None:
    get_client.cache_clear()
