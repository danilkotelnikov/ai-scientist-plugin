"""CLI subcommands for ``vedix provider {add,list,remove,test,set-chain}``.

State lives under ``~/.vedix/byok/``:
- ``providers.json`` — declared providers, fallback chain, per-agent-class overrides
- ``secrets/<name>.key`` — provider API key, chmod 600 on POSIX

Each function in this module is also callable from Python for tests.
"""
from __future__ import annotations
import json
import os
import stat
import time
from pathlib import Path


def _byok_root() -> Path:
    root = Path(os.environ.get("USERPROFILE") or os.environ["HOME"]) / ".vedix" / "byok"
    (root / "secrets").mkdir(parents=True, exist_ok=True)
    return root


def _providers_json_path() -> Path:
    return _byok_root() / "providers.json"


def _load_config() -> dict:
    p = _providers_json_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"providers": [], "chain": [], "per_agent_class": {}}


def _save_config(cfg: dict) -> None:
    p = _providers_json_path()
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _save_secret(name: str, secret: str) -> Path:
    p = _byok_root() / "secrets" / f"{name}.key"
    p.write_text(secret, encoding="utf-8")
    if os.name != "nt":
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return p


def add_provider(name: str, *, api_key: str, confirm: bool = True, **kwargs) -> None:
    cfg = _load_config()
    if any(p["name"] == name for p in cfg["providers"]):
        if confirm:
            resp = input(f"provider {name} already exists. Overwrite? [y/N]: ")
            if resp.strip().lower() != "y":
                return
        cfg["providers"] = [p for p in cfg["providers"] if p["name"] != name]
    _save_secret(name, api_key)
    entry = {"name": name, "added_at": time.time(), **kwargs}
    cfg["providers"].append(entry)
    if not cfg["chain"]:
        cfg["chain"] = [name]
    _save_config(cfg)
    print(f"[provider add] {name} configured")


def list_providers() -> list[dict]:
    return _load_config()["providers"]


def remove_provider(name: str, *, confirm: bool = True) -> None:
    cfg = _load_config()
    if confirm:
        resp = input(f"remove {name}? [y/N]: ")
        if resp.strip().lower() != "y":
            return
    cfg["providers"] = [p for p in cfg["providers"] if p["name"] != name]
    cfg["chain"] = [n for n in cfg["chain"] if n != name]
    _save_config(cfg)
    secret = _byok_root() / "secrets" / f"{name}.key"
    if secret.exists():
        secret.unlink()
    print(f"[provider remove] {name} removed")


def set_chain(names: list[str]) -> None:
    cfg = _load_config()
    known = {p["name"] for p in cfg["providers"]}
    unknown = set(names) - known
    if unknown:
        raise ValueError(f"unknown providers: {unknown}")
    cfg["chain"] = names
    _save_config(cfg)
    print(f"[provider chain] {' -> '.join(names)}")


async def test_provider(name: str) -> bool:
    """Send a tiny prompt to the named provider; return True if successful."""
    from .. import factory
    from ..base import ChatRequest, Message

    adapter = factory.build_adapter(name)
    try:
        await adapter.chat(
            ChatRequest(
                messages=[Message(role="user", content="hi")],
                model=factory.default_model(name),
                max_tokens=10,
            )
        )
        print(f"[provider test] {name} OK")
        return True
    except Exception as e:
        print(f"[provider test] {name} FAIL: {e}")
        return False
