"""JSONL cost ledger — one line per dispatched call.

Lives at ``~/.vedix/byok/cost_ledger.jsonl``. ``vedix cost report`` aggregates
this file by provider / model / agent_class / day to surface running spend.
Pricing tables (USD per 1M tokens) are rough; ``vedix update-prices`` re-fetches
from each provider's public pricing page quarterly.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

# Pricing per 1M tokens (input, output) — refreshed quarterly via vedix update-prices.
PRICING_USD_PER_M: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {"claude-opus-4": (15.0, 75.0), "claude-sonnet-4": (3.0, 15.0)},
    "openai": {"gpt-5": (5.0, 15.0), "gpt-5-xhigh": (10.0, 30.0)},
    "google": {"gemini-2.5-pro": (1.25, 5.0)},
    "deepseek": {"deepseek-chat": (0.14, 0.28), "deepseek-reasoner": (0.55, 2.19)},
    "qwen": {"qwen-max": (0.5, 1.5)},
    "moonshot": {"moonshot-v1-128k": (1.0, 3.0)},
    "zhipu": {"glm-4": (0.5, 1.5)},
    "gigachat": {"GigaChat-Pro": (0.5, 1.5)},
    "yandexgpt": {"yandexgpt": (0.4, 1.2)},
    "mistral": {"mistral-large-latest": (2.0, 6.0)},
    "cohere": {"command-r-plus": (3.0, 15.0)},
    "openrouter": {},  # OpenRouter passes through upstream provider pricing
    "together": {},
    "local": {},
}


def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])


class CostLedger:
    def __init__(self, path: Path | None = None):
        self.path = path or _home() / ".vedix" / "byok" / "cost_ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        provider: str,
        model: str,
        agent_class: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        prices = PRICING_USD_PER_M.get(provider, {}).get(model, (0.0, 0.0))
        cost = (input_tokens / 1_000_000) * prices[0] + (output_tokens / 1_000_000) * prices[1]
        entry = {
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "agent_class": agent_class,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
