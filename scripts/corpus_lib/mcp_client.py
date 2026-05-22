"""Lightweight MCP stdio JSON-RPC client.

Used by ``scripts/corpus_lib/acquisition.py`` to call Anna's Archive (and
any other MCP) from a standalone Python script outside the Claude / Codex
host. Spawns the MCP server as a subprocess, performs the protocol
handshake, and exposes ``call_tool(name, arguments)`` for downstream code.

Why this exists
---------------
The Vedix scripts (``scripts/prepare_corpus.py`` and friends) run as
plain Python — not inside a Claude Code agent dispatch. The MCPs registered
in ``~/.claude.json`` / ``~/.codex/config.toml`` are owned by the *host*,
not visible to the script's process. To talk to ``annas-mcp`` from a
script, the script has to spawn its own copy of the server.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional


class MCPClient:
    """Minimal async MCP stdio client.

    Usage::

        async with MCPClient(command="npx", args=["-y", "annas-mcp", "mcp"],
                              env={"ANNAS_SECRET_KEY": "..."}) as client:
            tools = await client.list_tools()
            out = await client.call_tool("article_search",
                                          {"query": "catalysis", "limit": 10})
    """

    def __init__(
        self,
        *,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        startup_timeout: float = 60.0,
    ) -> None:
        self.command = command
        self.args = args
        # Inherit the parent env so PATH / npm caches / etc work, then merge
        # the caller's overrides on top.
        merged_env: dict[str, str] = {**os.environ}
        if env:
            merged_env.update(env)
        self.env = merged_env
        self.startup_timeout = startup_timeout
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id = 1
        # Serialize requests so one call_tool can't interleave with another
        # in the middle of the handshake.
        self._lock = asyncio.Lock()

    # -- lifecycle ------------------------------------------------------ #

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @staticmethod
    def _resolve_command_on_windows(command: str) -> str:
        """On Windows, asyncio.create_subprocess_exec() does NOT apply PATHEXT,
        so a bare ``npx`` / ``npm`` / ``uvx`` / ``mempalace-mcp`` isn't found
        even though the shim is on PATH (as ``npx.cmd``, ``npm.cmd``, …).
        Walk PATH manually with the PATHEXT-derived suffix list."""
        import os as _os
        import shutil as _shutil
        if _os.name != "nt":
            return command
        if Path(command).is_file():
            return command
        # First try whatever-is-on-PATH directly
        which = _shutil.which(command)
        if which:
            return which
        # Try each Windows shim suffix in PATHEXT
        pathext = _os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
        for ext in pathext:
            ext = ext.strip()
            if not ext:
                continue
            candidate = _shutil.which(command + ext.lower())
            if candidate:
                return candidate
        return command  # last-resort: hand it to subprocess and let it fail loudly

    async def connect(self) -> None:
        """Spawn the server and run the MCP initialize / initialized handshake."""
        resolved_cmd = self._resolve_command_on_windows(self.command)
        self._proc = await asyncio.create_subprocess_exec(
            resolved_cmd,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
        )

        # Initialize handshake.
        init_id = self._next_id
        self._next_id += 1
        await self._send_raw({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "vedix-corpus-prep", "version": "3.0.0"},
            },
        })
        # Wait for the matching response (skipping any unrelated server-driven
        # notifications). Time-bounded so a hung server doesn't block forever.
        await asyncio.wait_for(self._wait_for_response(init_id), timeout=self.startup_timeout)
        # Tell the server we're ready for tool traffic.
        await self._send_raw({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

    async def close(self) -> None:
        if not self._proc:
            return
        try:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        except ProcessLookupError:
            pass
        self._proc = None

    # -- protocol ------------------------------------------------------- #

    async def _send_raw(self, payload: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("MCPClient is not connected")
        line = (json.dumps(payload) + "\n").encode("utf-8")
        self._proc.stdin.write(line)
        await self._proc.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("MCPClient is not connected")
        line = await self._proc.stdout.readline()
        if not line:
            stderr = b""
            if self._proc.stderr:
                try:
                    stderr = await asyncio.wait_for(self._proc.stderr.read(8192), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
            raise RuntimeError(f"MCP server '{self.command}' exited unexpectedly. stderr={stderr.decode('utf-8', errors='replace')!r}")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"MCP server emitted non-JSON line: {line!r}") from exc

    async def _wait_for_response(self, request_id: int) -> dict[str, Any]:
        """Read messages until we see the response matching ``request_id``.

        MCP servers can emit notifications (no ``id`` field) before the
        actual response; we silently drain those.
        """
        while True:
            msg = await self._read_message()
            if msg.get("id") == request_id:
                if "error" in msg:
                    raise RuntimeError(f"MCP error for id={request_id}: {msg['error']}")
                return msg.get("result", {})
            # Notification or unrelated; ignore.

    # -- public API ----------------------------------------------------- #

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            await self._send_raw({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/list",
            })
            result = await asyncio.wait_for(
                self._wait_for_response(request_id),
                timeout=self.startup_timeout,
            )
        return result.get("tools", [])

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Invoke an MCP tool and return its result payload."""
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            await self._send_raw({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            return await asyncio.wait_for(
                self._wait_for_response(request_id),
                timeout=timeout,
            )


def extract_text_from_mcp_result(result: dict[str, Any]) -> str:
    """Pull the ``text`` payload out of an MCP tool result.

    MCP tool responses look like::

        {"content": [{"type": "text", "text": "..."}], "isError": false}

    Some servers also wrap structured JSON inside the ``text`` field. Caller
    decides whether to ``json.loads`` it.
    """
    content = result.get("content") or []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    return ""
