"""Factory — builds adapters by name from ``providers.json`` + secrets dir.

The factory is the single point where ``provider name`` -> ``ProviderAdapter``
mapping happens. ``build_router()`` reads ``~/.vedix/byok/providers.json`` and
returns a fully-configured ``ProviderRouter`` (chain + per-agent overrides +
cost ledger).

Adapter imports are deferred to ``__getattr__`` so importing this module
doesn't pull in 14 SDKs at startup. Only adapters whose providers are listed
in ``providers.json`` get instantiated.
"""
from __future__ import annotations
import json
from typing import TYPE_CHECKING

from .cli.provider import _byok_root
from .cost_ledger import CostLedger
from .router import ProviderRouter

if TYPE_CHECKING:
    from .base import ProviderAdapter


DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-20250514",
    "openai": "gpt-5",
    "google": "gemini-2.5-pro",
    "openrouter": "anthropic/claude-opus-4",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-max",
    "moonshot": "moonshot-v1-128k",
    "zhipu": "glm-4-plus",
    "gigachat": "GigaChat-Pro",
    "yandexgpt": "yandexgpt",
    "mistral": "mistral-large-latest",
    "cohere": "command-r-plus",
    "local": "llama3",
}


def default_model(name: str) -> str:
    return DEFAULT_MODELS.get(name, "default")


def _load_secret(name: str) -> str:
    return (_byok_root() / "secrets" / f"{name}.key").read_text(encoding="utf-8").strip()


# Maps provider name -> "(module_path, class_name)" so each adapter is
# imported only when its provider is actually requested.
_ADAPTER_REGISTRY: dict[str, tuple[str, str]] = {
    "anthropic": (".adapters.anthropic_adapter", "AnthropicAdapter"),
    "openai": (".adapters.openai_adapter", "OpenAIAdapter"),
    "google": (".adapters.google_adapter", "GoogleAdapter"),
    "openrouter": (".adapters.openrouter_adapter", "OpenRouterAdapter"),
    "together": (".adapters.together_adapter", "TogetherAdapter"),
    "deepseek": (".adapters.deepseek_adapter", "DeepSeekAdapter"),
    "qwen": (".adapters.qwen_adapter", "QwenAdapter"),
    "moonshot": (".adapters.moonshot_adapter", "MoonshotAdapter"),
    "zhipu": (".adapters.zhipu_adapter", "ZhipuAdapter"),
    "gigachat": (".adapters.gigachat_adapter", "GigaChatAdapter"),
    "yandexgpt": (".adapters.yandexgpt_adapter", "YandexGPTAdapter"),
    "mistral": (".adapters.mistral_adapter", "MistralAdapter"),
    "cohere": (".adapters.cohere_adapter", "CohereAdapter"),
    "local": (".adapters.local_adapter", "LocalAdapter"),
}


def _resolve_adapter_class(name: str):
    from importlib import import_module

    mod_path, cls_name = _ADAPTER_REGISTRY[name]
    mod = import_module(mod_path, package="plugins.vedix.mcp.lib.orchestrator.byok")
    return getattr(mod, cls_name)


def build_adapter(name: str, **extra) -> "ProviderAdapter":
    cls = _resolve_adapter_class(name)
    secret = _load_secret(name)
    if name == "gigachat":
        return cls(credentials=secret, **extra)
    if name == "yandexgpt":
        cfg = json.loads((_byok_root() / "providers.json").read_text(encoding="utf-8"))
        folder_id = next(
            (p.get("folder_id", "") for p in cfg["providers"] if p["name"] == name),
            "",
        )
        return cls(api_key=secret, folder_id=folder_id)
    if name == "local":
        cfg = json.loads((_byok_root() / "providers.json").read_text(encoding="utf-8"))
        base_url = next(
            (p.get("base_url") for p in cfg["providers"] if p["name"] == name),
            "http://localhost:8000/v1",
        )
        return cls(api_key=secret, base_url=base_url, **extra)
    return cls(api_key=secret)


def build_router() -> ProviderRouter:
    cfg = json.loads((_byok_root() / "providers.json").read_text(encoding="utf-8"))
    chain = [build_adapter(name) for name in cfg.get("chain", [])]
    per_agent = {
        k: [build_adapter(n) for n in v]
        for k, v in cfg.get("per_agent_class", {}).items()
    }
    return ProviderRouter(chain=chain, per_agent_class=per_agent, cost_ledger=CostLedger())
