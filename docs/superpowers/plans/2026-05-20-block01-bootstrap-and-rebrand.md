# Block 1 — Bootstrap + Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rename `ai-scientist-plugin` → `vedix` across the repo, package name, MCP namespace, data directories, and slash command surface, with a migration helper that detects v2.x installs and moves state forward.

**Architecture:** Bottom-up rename. Start with the package manifest, propagate to the MCP server's `serverInfo.name`, update every grep-hit of the old strings, build a migration helper script users invoke on first v3.0 launch, and add a 6-month-lived deprecation stub at the old repo.

**Tech Stack:** Python 3.11+, no new dependencies. Migration helper uses only `pathlib`, `shutil`, `json`, `subprocess`.

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §2.

---

## File structure

| File | Action |
|---|---|
| `plugins/vedix/` | Rename of `plugins/ai-scientist/` (directory rename) |
| `plugins/vedix/.claude-plugin/plugin.json` | Modify: `name` → `vedix`; `version` → `3.0.0`; `commands.aiScientist` → `commands.vedix` |
| `gemini-extension.json` | Modify: `name` → `vedix`; version 3.0.0 |
| `plugins/vedix/mcp/server.py` | Modify: `serverInfo.name = "vedix"`, version 3.0.0; rename `mcp__ai-scientist__*` tool names → `mcp__vedix__*` |
| `plugins/vedix/mcp/.mcp.json` | Modify: server key `ai-scientist` → `vedix` |
| `plugins/vedix/codex-config.toml.example` | Modify: `[mcp_servers.ai-scientist]` → `[mcp_servers.vedix]` |
| `scripts/bootstrap.ps1` + `scripts/bootstrap.sh` | Modify: path constants `~/.ai-scientist/` → `~/.vedix/`; repo URL placeholder; cache dir |
| `scripts/migrate_v2_to_v3.py` | Create: detect v2.x state, prompt user, migrate |
| `README.md` | Modify: rebrand, update all install commands |
| Old `ai-scientist-plugin` repo | Create deprecation stub (`README.md` redirect + frozen final v2.1.2 release tag) |

## Task 1: Rename plugin directory + manifest

**Files:**
- Rename: `plugins/ai-scientist/` → `plugins/vedix/`
- Modify: `plugins/vedix/.claude-plugin/plugin.json`
- Test: `tests/test_plugin_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_manifest.py
import json
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "vedix"

def test_plugin_renamed_to_vedix():
    assert PLUGIN_DIR.exists(), "plugins/vedix/ must exist after rename"
    manifest = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "vedix"
    assert manifest["version"].startswith("3.0")
    assert "vedix" in manifest.get("commands", {})
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_plugin_manifest.py -v
# Expected: FAIL (plugins/vedix/ does not yet exist)
```

- [ ] **Step 3: Execute rename**

```bash
git mv plugins/ai-scientist plugins/vedix
```

- [ ] **Step 4: Update manifest**

```json
{
  "name": "vedix",
  "version": "3.0.0",
  "description": "Vedix — research workbench that turns a topic into a venue-ready manuscript via cross-host CLI orchestration",
  "commands": {
    "vedix": { "description": "Run the full Vedix research pipeline" },
    "research": { "alias": "vedix" }
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_plugin_manifest.py -v
# Expected: PASS
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/.claude-plugin/plugin.json tests/test_plugin_manifest.py
git commit -m "feat(B1): rename ai-scientist plugin directory to vedix; bump to 3.0.0"
```

## Task 2: Rename MCP server identity + tool namespace

**Files:**
- Modify: `plugins/vedix/mcp/server.py:1-50` (serverInfo + tool names)
- Modify: `plugins/vedix/mcp/.mcp.json` (server key)
- Test: `tests/test_mcp_server_identity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_server_identity.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_mcp_server_renamed_to_vedix():
    server_py = (ROOT / "plugins" / "vedix" / "mcp" / "server.py").read_text(encoding="utf-8")
    assert '"name": "vedix"' in server_py or "'name': 'vedix'" in server_py
    assert '"version": "3.0' in server_py or "'version': '3.0" in server_py
    # All tool names should be mcp__vedix__*
    assert "mcp__ai-scientist__" not in server_py
    assert "mcp__vedix__" in server_py

def test_mcp_config_uses_vedix_key():
    cfg = json.loads((ROOT / "plugins" / "vedix" / "mcp" / ".mcp.json").read_text(encoding="utf-8"))
    assert "vedix" in cfg.get("mcpServers", {})
    assert "ai-scientist" not in cfg.get("mcpServers", {})
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_mcp_server_identity.py -v
# Expected: FAIL
```

- [ ] **Step 3: Update server.py**

Find the serverInfo block and rename:

```python
SERVER_INFO = {
    "name": "vedix",
    "version": "3.0.0",
}
```

Find every tool name and rename:

```python
# Before: "name": "mcp__ai-scientist__search_knowledge_index"
# After:  "name": "mcp__vedix__search_knowledge_index"
```

Use a search-and-replace across `server.py`:

```bash
# Linux/macOS
sed -i 's/mcp__ai-scientist__/mcp__vedix__/g' plugins/vedix/mcp/server.py
# Windows PowerShell
(Get-Content plugins/vedix/mcp/server.py) -replace 'mcp__ai-scientist__','mcp__vedix__' | Set-Content plugins/vedix/mcp/server.py -Encoding UTF8
```

- [ ] **Step 4: Update .mcp.json**

```json
{
  "mcpServers": {
    "vedix": {
      "command": "python",
      "args": ["${env:HOME}/.vedix/repo/plugins/vedix/mcp/server.py", "--mode", "stdio"]
    }
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_mcp_server_identity.py -v
# Expected: PASS
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/mcp/server.py plugins/vedix/mcp/.mcp.json tests/test_mcp_server_identity.py
git commit -m "feat(B1): rename MCP server identity + tool namespace to vedix"
```

## Task 3: Data directory rename + migration helper

**Files:**
- Create: `scripts/migrate_v2_to_v3.py`
- Test: `tests/test_migrate_v2_to_v3.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate_v2_to_v3.py
import json
import shutil
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from migrate_v2_to_v3 import migrate, detect_v2_state

def test_detect_v2_state_when_present(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".ai-scientist" / "palace").mkdir(parents=True)
    (home / ".ai-scientist" / "knowledge.db").write_bytes(b"sqlite")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    state = detect_v2_state()
    assert state["v2_root"] == home / ".ai-scientist"
    assert state["has_palace"] is True
    assert state["has_knowledge_db"] is True

def test_migrate_moves_state_to_v3(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".ai-scientist" / "palace").mkdir(parents=True)
    (home / ".ai-scientist" / "palace" / "drawer1.json").write_text('{"a": 1}')
    (home / ".ai-scientist" / "knowledge.db").write_bytes(b"sqlite")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    migrate(confirm=False)

    assert (home / ".vedix" / "palace" / "drawer1.json").exists()
    assert (home / ".vedix" / "knowledge.db").exists()
    # Old dir should be renamed to .ai-scientist.bak, not deleted
    assert (home / ".ai-scientist.bak").exists()
    assert not (home / ".ai-scientist").exists()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_migrate_v2_to_v3.py -v
# Expected: FAIL (migrate_v2_to_v3.py does not yet exist)
```

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/migrate_v2_to_v3.py
"""Migrate Vedix v2.x state to v3.0 layout."""
import os
import shutil
from pathlib import Path

def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def detect_v2_state() -> dict:
    v2 = _home() / ".ai-scientist"
    return {
        "v2_root": v2,
        "exists": v2.exists(),
        "has_palace": (v2 / "palace").exists(),
        "has_knowledge_db": (v2 / "knowledge.db").exists(),
        "has_corpus": (v2 / "corpus").exists(),
        "has_classifiers": (v2 / "classifiers").exists(),
    }

def migrate(confirm: bool = True) -> None:
    state = detect_v2_state()
    if not state["exists"]:
        print("[migrate] no v2.x install detected at ~/.ai-scientist — nothing to do")
        return

    v2 = state["v2_root"]
    v3 = _home() / ".vedix"

    if v3.exists():
        print(f"[migrate] {v3} already exists; refusing to overwrite")
        return

    if confirm:
        resp = input(f"[migrate] move {v2} → {v3}? [y/N]: ").strip().lower()
        if resp != "y":
            print("[migrate] aborted by user")
            return

    print(f"[migrate] moving {v2} → {v3}")
    shutil.move(str(v2), str(v3))

    # Leave a breadcrumb at the old location so users know what happened
    backup_marker = _home() / ".ai-scientist.bak"
    backup_marker.mkdir(exist_ok=True)
    (backup_marker / "MIGRATED_TO_VEDIX.txt").write_text(
        f"This v2 directory was migrated to ~/.vedix/ on Vedix v3.0 install.\n"
        f"State is now at: {v3}\n"
    )
    print(f"[migrate] done. Breadcrumb at {backup_marker}")

if __name__ == "__main__":
    import sys
    confirm = "--no-confirm" not in sys.argv
    migrate(confirm=confirm)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_migrate_v2_to_v3.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_v2_to_v3.py tests/test_migrate_v2_to_v3.py
git commit -m "feat(B1): migrate_v2_to_v3.py helper script for ~/.ai-scientist → ~/.vedix/"
```

## Task 4: Wire migration helper into bootstrap

**Files:**
- Modify: `scripts/bootstrap.ps1` (call migrate at install end)
- Modify: `scripts/bootstrap.sh` (call migrate at install end)
- Test: manual integration test on a v2.x install

- [ ] **Step 1: Add to bootstrap.sh**

After the existing install steps, before final echo, add:

```bash
# B1: v2 → v3 migration
if [ -d "$HOME/.ai-scientist" ] && [ ! -d "$HOME/.vedix" ]; then
  echo ""
  echo "[bootstrap] detected v2.x install at ~/.ai-scientist"
  python "$PLUG/scripts/migrate_v2_to_v3.py"
fi
```

- [ ] **Step 2: Add to bootstrap.ps1**

```powershell
# B1: v2 → v3 migration
$v2Dir = Join-Path $env:USERPROFILE ".ai-scientist"
$v3Dir = Join-Path $env:USERPROFILE ".vedix"
if ((Test-Path $v2Dir) -and -not (Test-Path $v3Dir)) {
  Write-Host ""
  Write-Host "[bootstrap] detected v2.x install at $v2Dir"
  & python (Join-Path $Plug "scripts\migrate_v2_to_v3.py")
}
```

- [ ] **Step 3: Manual integration test**

Set up a temp HOME with a fake `~/.ai-scientist/` directory:

```bash
TMPHOME=$(mktemp -d)
mkdir -p "$TMPHOME/.ai-scientist/palace"
echo '{"test": 1}' > "$TMPHOME/.ai-scientist/palace/drawer.json"
HOME="$TMPHOME" bash scripts/bootstrap.sh
ls "$TMPHOME/.vedix/palace/"
# Expected: drawer.json
```

- [ ] **Step 4: Commit**

```bash
git add scripts/bootstrap.ps1 scripts/bootstrap.sh
git commit -m "feat(B1): bootstrap calls migrate_v2_to_v3.py when v2 state detected"
```

## Task 5: Cross-references in bootstrap + Codex config

**Files:**
- Modify: `scripts/bootstrap.ps1` (path constants)
- Modify: `scripts/bootstrap.sh` (path constants)
- Modify: `plugins/vedix/codex-config.toml.example` (server key)
- Modify: `gemini-extension.json` (name, version)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_install_path_rebrand.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_bootstrap_uses_vedix_paths():
    for f in ["scripts/bootstrap.ps1", "scripts/bootstrap.sh"]:
        content = (ROOT / f).read_text(encoding="utf-8")
        assert ".vedix" in content, f"{f} must reference ~/.vedix/"
        # The old name should only appear in migration context
        if ".ai-scientist" in content:
            assert "ai-scientist" in content and ("migrate" in content or "detect" in content), \
                f"{f} mentions ai-scientist outside migration context"

def test_codex_config_uses_vedix_key():
    content = (ROOT / "plugins" / "vedix" / "codex-config.toml.example").read_text(encoding="utf-8")
    assert "[mcp_servers.vedix]" in content
    assert "[mcp_servers.ai-scientist]" not in content
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_install_path_rebrand.py -v
# Expected: FAIL
```

- [ ] **Step 3: Apply path renames**

Sweep replace across bootstrap scripts and config templates:

```bash
sed -i 's|~/.ai-scientist|~/.vedix|g; s|/.ai-scientist|/.vedix|g; s|ai-scientist-plugin|vedix|g' \
  scripts/bootstrap.sh scripts/bootstrap.ps1
sed -i 's|\[mcp_servers\.ai-scientist\]|[mcp_servers.vedix]|g; s|AI_SCIENTIST_HOME|VEDIX_HOME|g' \
  plugins/vedix/codex-config.toml.example
```

(Manually retain the v2-detection block in bootstrap.* which intentionally keeps the old name for detection.)

- [ ] **Step 4: Update gemini-extension.json**

```json
{
  "name": "vedix",
  "version": "3.0.0",
  ...
}
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_install_path_rebrand.py tests/test_mcp_server_identity.py tests/test_plugin_manifest.py -v
# Expected: ALL PASS
```

- [ ] **Step 6: Commit**

```bash
git add scripts/bootstrap.ps1 scripts/bootstrap.sh plugins/vedix/codex-config.toml.example gemini-extension.json tests/test_install_path_rebrand.py
git commit -m "feat(B1): rebrand install paths + Codex/Gemini configs to vedix"
```

## Task 6: Deprecation stub for the old repo

**Files:**
- Create: `legacy/DEPRECATION_README.md` (will live at the root of the OLD repo after we move main to a new repo)
- Modify: None in vedix repo

- [ ] **Step 1: Draft the deprecation README**

Will be committed only to the legacy `ai-scientist-plugin` repo (not vedix). Content:

```markdown
# ai-scientist-plugin (v2.x) — deprecated

This plugin has been renamed to **Vedix** and lives at:

→ https://github.com/danilkotelnikov/vedix

For installation instructions, migration from v2.x, and the v3.0 changelog, see the new repo.

The final v2.x release tag (v2.1.2) is preserved at this URL for the next 6 months (until 2026-11-20). After that this repo is archived.

If you have an existing v2.x install, the v3.0 bootstrap auto-detects it and offers to migrate.
```

- [ ] **Step 2: Note in Vedix repo for future operator**

Create `docs/legacy/README-deprecation-stub.md`:

```markdown
# Deprecation stub for old `ai-scientist-plugin` repo

Push this content to the legacy GitHub repo's README.md once v3.0 ships:

[paste of DEPRECATION_README.md above]

After 6 months (2026-11-20), archive the legacy repo via GitHub Settings → Archive.
```

- [ ] **Step 3: Commit**

```bash
mkdir -p docs/legacy/
# write the file with the deprecation stub text
git add docs/legacy/README-deprecation-stub.md
git commit -m "docs(B1): deprecation-stub content for legacy ai-scientist-plugin repo"
```

## Task 7: v3.0 version bump verification

**Files:** all files modified above

- [ ] **Step 1: Write integration test**

```python
# tests/test_v3_version_consistency.py
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_all_version_strings_are_3_0_0():
    """Every place that declares a version must say 3.0.0."""
    plugin_manifest = json.loads((ROOT / "plugins" / "vedix" / ".claude-plugin" / "plugin.json").read_text())
    assert plugin_manifest["version"].startswith("3.0")

    gemini_manifest = json.loads((ROOT / "gemini-extension.json").read_text())
    assert gemini_manifest["version"].startswith("3.0")

    server_py = (ROOT / "plugins" / "vedix" / "mcp" / "server.py").read_text()
    assert re.search(r'"version"\s*:\s*"3\.0', server_py) or re.search(r"'version'\s*:\s*'3\.0", server_py)
```

- [ ] **Step 2: Run the test**

```
pytest tests/test_v3_version_consistency.py -v
# Expected: PASS (we already bumped these in earlier tasks)
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_v3_version_consistency.py
git commit -m "test(B1): assert v3.0.0 version stamped across all manifests"
```

## Block 1 acceptance criteria

Block 1 is complete when:

- [ ] `pytest tests/test_plugin_manifest.py tests/test_mcp_server_identity.py tests/test_install_path_rebrand.py tests/test_migrate_v2_to_v3.py tests/test_v3_version_consistency.py -v` all pass
- [ ] `grep -r "ai-scientist" plugins/ scripts/ | grep -v migrate | grep -v ai-scientist.bak` returns nothing
- [ ] Manual install from clean `~/` succeeds: `bash scripts/bootstrap.sh` → `~/.vedix/` created
- [ ] Manual migration from v2.1.2 install succeeds (prompt + move)
- [ ] `/vedix linear regression on synthetic data` runs end-to-end with all 9 MCPs reachable
- [ ] Git tag `v3.0.0-block1` pushed
