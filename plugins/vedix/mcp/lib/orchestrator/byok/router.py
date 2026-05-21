"""Provider router with fallback chain + per-agent-class override.

For each chat request the router walks its configured chain of adapters. An
adapter is skipped early when it lacks a capability the request requires
(tools / structured output). On ``RateLimited`` / ``ProviderUnavailable`` /
``AuthError`` the router moves to the next provider; on ``ContextOverflow``
it re-raises (next provider almost certainly has similar context limits, so
the caller needs to shrink the prompt). All successful calls are appended
to the JSONL cost ledger.
"""
from __future__ import annotations
import asyncio
import logging
from typing import AsyncIterator

from .base import ChatRequest, ChatResponse, ProviderAdapter
from .cost_ledger import CostLedger
from .exceptions import (
    AuthError,
    CapabilityMissing,
    ContextOverflow,
    ProviderUnavailable,
    RateLimited,
)

logger = logging.getLogger(__name__)


class ProviderRouter:
    def __init__(
        self,
        chain: list[ProviderAdapter],
        per_agent_class: dict[str, list[ProviderAdapter]] | None = None,
        cost_ledger: CostLedger | None = None,
    ):
        self.chain = chain
        self.per_agent_class = per_agent_class or {}
        self.cost_ledger = cost_ledger

    def _resolve_chain(self, agent_class: str | None) -> list[ProviderAdapter]:
        if agent_class and agent_class in self.per_agent_class:
            return self.per_agent_class[agent_class]
        return self.chain

    async def chat(self, req: ChatRequest, agent_class: str | None = None) -> ChatResponse:
        chain = self._resolve_chain(agent_class)
        last_err: Exception | None = None
        for adapter in chain:
            caps = adapter.capabilities()
            if req.tools and not caps.supports_tools:
                logger.warning("skip %s: no tool support, request had tools", adapter.name)
                last_err = CapabilityMissing(adapter.name, "tools")
                continue
            if req.response_schema and not caps.supports_structured_output:
                logger.warning(
                    "skip %s: no structured-output, request had schema", adapter.name
                )
                last_err = CapabilityMissing(adapter.name, "structured_output")
                continue
            try:
                resp = await adapter.chat(req)
                if self.cost_ledger:
                    self.cost_ledger.record(
                        provider=adapter.name,
                        model=resp.model,
                        agent_class=agent_class or "default",
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                    )
                return resp
            except RateLimited as e:
                logger.warning(
                    "%s rate-limited; retry_after=%s; trying next", adapter.name, e.retry_after
                )
                last_err = e
                if e.retry_after and len(chain) == 1:
                    # Single-provider chain: honor retry-after and try again.
                    await asyncio.sleep(min(e.retry_after, 30))
            except (ProviderUnavailable, AuthError) as e:
                logger.warning("%s unavailable: %s; trying next", adapter.name, e)
                last_err = e
            except ContextOverflow:
                # Context overflow is roughly provider-agnostic — the next
                # adapter likely has similar limits. Re-raise so the caller
                # shrinks the prompt rather than burning quota.
                raise
        raise last_err or ProviderUnavailable("router", "no providers configured")

    async def stream(
        self, req: ChatRequest, agent_class: str | None = None
    ) -> AsyncIterator[str]:
        chain = self._resolve_chain(agent_class)
        for adapter in chain:
            try:
                async for chunk in adapter.stream(req):
                    yield chunk
                return
            except (RateLimited, ProviderUnavailable, AuthError):
                continue
        raise ProviderUnavailable("router", "no providers could stream")
