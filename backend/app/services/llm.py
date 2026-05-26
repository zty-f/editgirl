"""LLM 客户端 — 支持多 provider。

provider="openai":任何 OpenAI 兼容 endpoint
  - OpenAI / DeepSeek / 通义千问 / 智谱 / Kimi / Ollama / 自建 vLLM

provider="anthropic":Anthropic Claude(原生 API)
  - claude-opus-4-7 / claude-sonnet-4-6 / claude-haiku-4-5

配置走 settings_store(前端动态修改不重启生效)。
"""
from __future__ import annotations
import json
from typing import Any
from openai import OpenAI, AsyncOpenAI
from anthropic import Anthropic, AsyncAnthropic
from . import settings_store


# ---------- 客户端构造 ----------
def _make_openai_client(async_mode: bool = False):
    s = settings_store.get_settings()
    cls = AsyncOpenAI if async_mode else OpenAI
    return cls(base_url=s["OPENAI_BASE_URL"], api_key=s["OPENAI_API_KEY"])


def _make_anthropic_client(async_mode: bool = False):
    s = settings_store.get_settings()
    cls = AsyncAnthropic if async_mode else Anthropic
    # Anthropic 默认 base_url,除非用户改了
    kwargs = {"api_key": s["OPENAI_API_KEY"]}  # 复用 API_KEY 字段
    base = s["OPENAI_BASE_URL"]
    if base and "anthropic" not in base and base != "https://api.anthropic.com":
        kwargs["base_url"] = base
    return cls(**kwargs)


def _current_provider() -> str:
    return settings_store.get_settings().get("LLM_PROVIDER", "openai")


def _current_model() -> str:
    return settings_store.get_settings()["LLM_MODEL"]


# ---------- 同步 chat(用于 chat agent / 测试) ----------
def chat(messages: list[dict], tools: list[dict] | None = None, **kwargs) -> Any:
    provider = _current_provider()
    if provider == "anthropic":
        return _chat_anthropic(messages, **kwargs)
    return _chat_openai(messages, tools=tools, **kwargs)


def _chat_openai(messages, tools=None, **kwargs):
    client = _make_openai_client(async_mode=False)
    params = {"model": _current_model(), "messages": messages}
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"
    params.update(kwargs)
    resp = client.chat.completions.create(**params)
    return resp.choices[0].message


def _chat_anthropic(messages, **kwargs):
    """Anthropic 用 Messages API,把 system 拆出来。"""
    client = _make_anthropic_client(async_mode=False)
    system = ""
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system += m["content"] + "\n"
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    params = {
        "model": _current_model(),
        "max_tokens": kwargs.get("max_tokens", 4096),
        "system": system.strip(),
        "messages": msgs,
    }
    resp = client.messages.create(**params)
    # 模拟 OpenAI 的 message.content 接口
    class _M:
        content = resp.content[0].text if resp.content else ""
    return _M()


# ---------- JSON 解析 ----------
def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        for open_c, close_c in [("[", "]"), ("{", "}")]:
            i = text.find(open_c)
            j = text.rfind(close_c)
            if i >= 0 and j > i:
                try:
                    return json.loads(text[i : j + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"无法解析 LLM 返回的 JSON: {text[:200]}") from e


def chat_json(system: str, user: str, **kwargs) -> Any:
    msg = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        **kwargs,
    )
    return _extract_json(msg.content or "")


# ---------- 显式参数版(测试用,不读 settings_store,不污染 DB) ----------
def chat_explicit(provider: str, base_url: str, api_key: str, model: str,
                  messages: list[dict], **kwargs) -> Any:
    """用显式参数调 LLM,不读 DB。供 /settings/test 用。"""
    if provider == "anthropic":
        kwargs_a = {"api_key": api_key}
        if base_url and "api.anthropic.com" not in base_url:
            kwargs_a["base_url"] = base_url
        client = Anthropic(**kwargs_a)
        system = ""
        msgs = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        params = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 50),
            "messages": msgs,
        }
        if system.strip():
            params["system"] = system.strip()
        resp = client.messages.create(**params)
        class _M: content = resp.content[0].text if resp.content else ""
        return _M()
    # openai
    client = OpenAI(base_url=base_url, api_key=api_key)
    params = {"model": model, "messages": messages}
    params.update(kwargs)
    resp = client.chat.completions.create(**params)
    return resp.choices[0].message


# ---------- 异步(用于校对并发) ----------
async def achat_json(system: str, user: str, **kwargs) -> Any:
    provider = _current_provider()
    if provider == "anthropic":
        client = _make_anthropic_client(async_mode=True)
        params = {
            "model": _current_model(),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        resp = await client.messages.create(**params)
        text = resp.content[0].text if resp.content else ""
    else:
        client = _make_openai_client(async_mode=True)
        params = {
            "model": _current_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        params.update(kwargs)
        resp = await client.chat.completions.create(**params)
        text = resp.choices[0].message.content or ""
    return _extract_json(text)
