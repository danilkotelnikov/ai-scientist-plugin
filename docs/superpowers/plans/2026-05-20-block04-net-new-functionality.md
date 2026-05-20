# Block 4 — Net-New Functionality Implementation Plan (§5 minus §5.3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement the 5 net-new tracks from §5 that aren't the register classifier (which is Block 5): form-driven pre-experimental dialog (§5.1), post-experiment numerical claim audit (§5.2), per-artifact rationale files (§5.4), codebase-aware research mode (§5.5), public-result reproducibility audit (§5.6), and the absorbed v3.1 features (§5.7 web-UI hook, §5.8 IDE-plugin hook scaffolding — full UIs are Blocks 9/10; §5.9 pre-print auto-submit — full impl is Block 11; §5.10/5.11 federated/collab — full impl is Block 11). This block sets up the orchestrator-side hook points so Blocks 9–11 can plug in.

**Architecture:** Each track is one orchestrator module plus optional CLI subcommands. The form dialog uses Pydantic models so the web UI (B9) can reuse the same schema. The numerical audit reads `results.csv` + `experiment_stdout.txt` and matches numbers against manuscript claims via regex + tolerance. Rationale files are written by a new `rationale-writer` agent. Codebase-aware mode uses `mcp__vedix__analyze_codebase`. Reproducibility audit runs the experiment from clean state and re-compares numerics.

**Tech Stack:** Python 3.11+, Pydantic v2, regex, pandas (for results.csv), `mcp__vedix__analyze_codebase` (existing in v2.1).

**Spec source:** §5.1, 5.2, 5.4, 5.5, 5.6, 5.7 (hook), 5.8 (hook), 5.9 (CLI scaffolding).

---

## File structure

```
plugins/vedix/mcp/lib/orchestrator/
├── preflight_dialog.py          # §5.1 form-driven setup
├── numerical_audit.py           # §5.2 claim ↔ artifact verification
├── rationale_writer.py          # §5.4 per-artifact .rationale.md
├── codebase_research.py         # §5.5 codebase-aware research mode
├── reproducibility_audit.py     # §5.6 fresh-run audit
└── hooks/
    ├── webui_events.py          # §5.7 SSE event emitter (for Block 9 to consume)
    ├── ide_protocol.py          # §5.8 IDE-plugin JSON-RPC protocol stubs
    └── preprint_submit.py       # §5.9 CLI scaffolding for arxiv/biorxiv/osf
```

## Task 1: Form-driven pre-experimental dialog (§5.1)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/preflight_dialog.py`
- Test: `tests/net_new/test_preflight_dialog.py`

- [ ] **Step 1: Write test**

```python
# tests/net_new/test_preflight_dialog.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.preflight_dialog import (
    ExperimentSetup, validate_setup, get_setup_schema
)

def test_setup_validates_required_fields():
    setup = ExperimentSetup(
        topic="solvent polarity on Diels-Alder",
        discipline="chemistry",
        language="en",
        venue="preprint",
        hypothesis_style="exploratory",
        experiment_type="computational",
        primary_metric="reaction yield",
        expected_direction="increase",
        tolerance=0.05,
    )
    validate_setup(setup)  # no raise

def test_setup_rejects_invalid_discipline():
    with pytest.raises(ValueError, match="discipline"):
        ExperimentSetup(
            topic="x", discipline="invented-field", language="en", venue="preprint",
            hypothesis_style="confirmatory", experiment_type="empirical",
            primary_metric="x", expected_direction="increase", tolerance=0.01,
        )

def test_schema_exposed_for_webui():
    schema = get_setup_schema()
    assert "properties" in schema
    assert "topic" in schema["properties"]
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/preflight_dialog.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator

VALID_DISCIPLINES = {"chemistry", "biology", "medicine", "physics", "mathematics", "geology", "computer_science", "humanities"}
VALID_LANGUAGES = {"en", "ru", "es", "de", "fr", "zh", "ja"}
VALID_VENUES = {
    "preprint", "nature", "elsevier", "springer-nature", "taylor-francis", "frontiers",
    "wiley", "sage", "plos", "cell", "ieee", "acm", "acs", "mdpi", "revtex42",
    "rsc", "cambridge", "oup", "bmj", "jama", "gost-generic", "dan-ras", "uspekhi",
}

class ExperimentSetup(BaseModel):
    topic: str = Field(min_length=10, max_length=500)
    discipline: Literal["chemistry", "biology", "medicine", "physics", "mathematics", "geology", "computer_science", "humanities"]
    language: Literal["en", "ru", "es", "de", "fr", "zh", "ja"]
    venue: str
    hypothesis_style: Literal["confirmatory", "exploratory", "comparative", "descriptive"]
    experiment_type: Literal["empirical", "computational", "review", "theoretical"]
    primary_metric: str
    expected_direction: Literal["increase", "decrease", "no-change", "comparison"]
    tolerance: float = Field(gt=0, lt=1)
    codebase_path: str | None = None

    @field_validator("venue")
    @classmethod
    def _venue_known(cls, v: str) -> str:
        # Accept venue or venue:journal
        base = v.split(":", 1)[0]
        if base not in VALID_VENUES:
            raise ValueError(f"venue must be one of {sorted(VALID_VENUES)} (got {base!r})")
        return v

def validate_setup(setup: ExperimentSetup) -> None:
    if setup.experiment_type == "empirical" and setup.codebase_path is None:
        # Not strictly required, but a soft warning
        pass

def get_setup_schema() -> dict:
    return ExperimentSetup.model_json_schema()
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/preflight_dialog.py tests/net_new/test_preflight_dialog.py
git commit -m "feat(B4): §5.1 form-driven pre-experimental dialog with Pydantic schema"
```

## Task 2: Post-experiment numerical claim audit (§5.2)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/numerical_audit.py`
- Test: `tests/net_new/test_numerical_audit.py`

- [ ] **Step 1: Write test**

```python
# tests/net_new/test_numerical_audit.py
import pandas as pd
import pytest
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.numerical_audit import audit_claims

def test_audit_passes_when_numbers_match(tmp_path):
    (tmp_path / "results.csv").write_text("metric,value\naccuracy,0.853\nf1,0.792\n")
    manuscript = "Our model achieved 0.853 accuracy and 0.792 F1."
    report = audit_claims(manuscript_text=manuscript, results_path=tmp_path / "results.csv", tolerance_abs=1e-3)
    assert report["status"] == "ok"
    assert len(report["mismatches"]) == 0

def test_audit_flags_mismatch(tmp_path):
    (tmp_path / "results.csv").write_text("metric,value\naccuracy,0.853\n")
    manuscript = "Our model achieved 0.91 accuracy."
    report = audit_claims(manuscript_text=manuscript, results_path=tmp_path / "results.csv", tolerance_abs=1e-3)
    assert report["status"] == "blocked"
    assert len(report["mismatches"]) >= 1
    assert report["mismatches"][0]["claim_value"] == 0.91
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/numerical_audit.py
from __future__ import annotations
import re
import pandas as pd
from pathlib import Path
from typing import Optional

NUMBER_RE = re.compile(r"(\d+\.\d+|\d+(?:\.\d+)?[eE][-+]?\d+|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+(?:[eE][-+]?\d+)?)")

def _extract_numbers(text: str) -> list[float]:
    nums = []
    for m in NUMBER_RE.finditer(text):
        try:
            nums.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return nums

def audit_claims(*, manuscript_text: str, results_path: Path, tolerance_abs: float = 1e-3, tolerance_rel: float = 0.01) -> dict:
    if not results_path.exists():
        return {"status": "ok", "mismatches": [], "note": "no results.csv to audit"}
    df = pd.read_csv(results_path)
    artifact_values = []
    if "value" in df.columns:
        artifact_values = df["value"].tolist()
    else:
        for c in df.select_dtypes("number").columns:
            artifact_values.extend(df[c].tolist())

    claim_values = _extract_numbers(manuscript_text)
    mismatches = []
    for cv in claim_values:
        # Find the closest artifact value
        if not artifact_values:
            break
        closest = min(artifact_values, key=lambda a: abs(a - cv))
        abs_delta = abs(closest - cv)
        rel_delta = abs_delta / abs(closest) if closest != 0 else float("inf")
        if abs_delta > tolerance_abs and rel_delta > tolerance_rel:
            mismatches.append({
                "claim_value": cv, "closest_artifact_value": closest,
                "abs_delta": round(abs_delta, 6), "rel_delta": round(rel_delta, 6),
                "severity": "block" if rel_delta > 0.1 else "warn",
            })
    status = "blocked" if any(m["severity"] == "block" for m in mismatches) else ("warned" if mismatches else "ok")
    return {"status": status, "mismatches": mismatches}
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/numerical_audit.py tests/net_new/test_numerical_audit.py
git commit -m "feat(B4): §5.2 post-experiment numerical claim audit"
```

## Task 3: Rationale-writer (§5.4)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/rationale_writer.py`
- Test: `tests/net_new/test_rationale_writer.py`

- [ ] **Step 1: Write test**

```python
# tests/net_new/test_rationale_writer.py
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.rationale_writer import write_rationale

@pytest.mark.asyncio
async def test_write_rationale(tmp_path):
    artifact_path = tmp_path / "hypothesis.md"
    artifact_path.write_text("Hypothesis: temperature affects yield")
    fake_response = type("R", (), {"content": "## Why this exists\n- the experimenter chose this..."})()
    with patch("plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
               new=AsyncMock(return_value=fake_response)):
        rationale = await write_rationale(
            artifact_path=artifact_path,
            artifact_kind="hypothesis",
            producing_agent="hypothesizer",
            decisions=[{"option": "exploratory", "alternative": "confirmatory"}],
        )
    assert rationale.exists()
    assert "Why this exists" in rationale.read_text()
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/rationale_writer.py
from __future__ import annotations
from pathlib import Path
from .dispatch import dispatch_agent

PROMPT = """Write a `.rationale.md` companion file for this {artifact_kind} artifact produced by the `{producing_agent}` agent.

The rationale should cover:
1. Why this artifact exists (which research question / hypothesis it serves)
2. What decisions the agent made (competing options considered, choice rationale)
3. What evidence the agent relied on (papers, numerical values, prior work)
4. What the human researcher should verify (3-5 specific check-this items)
5. What the agent is uncertain about (open questions, hedges)

Artifact content:
```
{artifact_text}
```

Decision log:
{decisions}

Output the rationale as markdown, ≤ 300 words.
"""

async def write_rationale(*, artifact_path: Path, artifact_kind: str, producing_agent: str, decisions: list[dict]) -> Path:
    artifact_text = artifact_path.read_text(encoding="utf-8")
    prompt = PROMPT.format(
        artifact_kind=artifact_kind,
        producing_agent=producing_agent,
        artifact_text=artifact_text[:4000],
        decisions="\n".join(f"- chose {d.get('option')} over {d.get('alternative')}" for d in decisions),
    )
    resp = await dispatch_agent(agent_type="rationale-writer", prompt=prompt)
    out = artifact_path.with_suffix(artifact_path.suffix + ".rationale.md")
    out.write_text(resp.content, encoding="utf-8")
    return out
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/rationale_writer.py tests/net_new/test_rationale_writer.py
git commit -m "feat(B4): §5.4 rationale-writer for per-artifact .rationale.md companions"
```

## Task 4: Codebase-aware research mode (§5.5)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/codebase_research.py`
- Test: `tests/net_new/test_codebase_research.py`

- [ ] **Step 1: Write test**

```python
# tests/net_new/test_codebase_research.py
import pytest
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.codebase_research import CodebaseContext

def test_codebase_context_loads(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "model.py").write_text("def train(): pass\n")
    (tmp_path / "src" / "data.py").write_text("def load(): pass\n")
    ctx = CodebaseContext.from_path(tmp_path)
    assert "src/model.py" in ctx.list_files() or "src\\model.py" in ctx.list_files()
    funcs = ctx.list_functions()
    assert any(f["name"] == "train" for f in funcs)

def test_module_lookup(tmp_path):
    (tmp_path / "exp.py").write_text("def run_experiment(seed=42):\n    return seed * 2\n")
    ctx = CodebaseContext.from_path(tmp_path)
    func = ctx.find_function("run_experiment")
    assert func is not None
    assert func["name"] == "run_experiment"
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/codebase_research.py
from __future__ import annotations
import ast
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class CodebaseContext:
    root: Path
    files: list[Path] = field(default_factory=list)
    _funcs: list[dict] = field(default_factory=list)

    @classmethod
    def from_path(cls, root: Path) -> "CodebaseContext":
        root = Path(root)
        files = list(root.rglob("*.py"))
        ctx = cls(root=root, files=files)
        ctx._index()
        return ctx

    def _index(self):
        for f in self.files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._funcs.append({"file": str(f.relative_to(self.root)), "name": node.name, "lineno": node.lineno})
                elif isinstance(node, ast.AsyncFunctionDef):
                    self._funcs.append({"file": str(f.relative_to(self.root)), "name": node.name, "lineno": node.lineno})
                elif isinstance(node, ast.ClassDef):
                    self._funcs.append({"file": str(f.relative_to(self.root)), "name": node.name, "lineno": node.lineno, "kind": "class"})

    def list_files(self) -> list[str]:
        return [str(f.relative_to(self.root)) for f in self.files]

    def list_functions(self) -> list[dict]:
        return self._funcs

    def find_function(self, name: str) -> dict | None:
        for f in self._funcs:
            if f["name"] == name:
                return f
        return None
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/codebase_research.py tests/net_new/test_codebase_research.py
git commit -m "feat(B4): §5.5 codebase-aware research mode — AST index of Python sources"
```

## Task 5: Reproducibility audit (§5.6)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/reproducibility_audit.py`
- Test: `tests/net_new/test_reproducibility_audit.py`

- [ ] **Step 1: Write test**

```python
# tests/net_new/test_reproducibility_audit.py
import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch
from plugins.vedix.mcp.lib.orchestrator.reproducibility_audit import audit_reproducibility

def test_audit_passes_when_results_match(tmp_path):
    (tmp_path / "experiment.py").write_text(
        "import json, pathlib\n"
        "pathlib.Path('results.csv').write_text('metric,value\\naccuracy,0.85\\n')\n"
    )
    (tmp_path / "results.csv").write_text("metric,value\naccuracy,0.85\n")
    report = audit_reproducibility(
        experiment_dir=tmp_path,
        claimed_results=tmp_path / "results.csv",
        sandbox_dir=tmp_path / "sandbox",
    )
    assert report["status"] == "ok"
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/reproducibility_audit.py
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
import pandas as pd

def audit_reproducibility(*, experiment_dir: Path, claimed_results: Path, sandbox_dir: Path) -> dict:
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    sandbox_dir.mkdir(parents=True)
    # Copy experiment.py + requirements.txt into sandbox
    for fn in ("experiment.py", "requirements.txt"):
        src = experiment_dir / fn
        if src.exists():
            shutil.copy2(src, sandbox_dir / fn)

    # Create venv + install + run
    try:
        subprocess.run(["python", "-m", "venv", str(sandbox_dir / "venv")], check=True)
        pip = sandbox_dir / "venv" / ("Scripts" if (sandbox_dir / "venv" / "Scripts").exists() else "bin") / "pip"
        py = sandbox_dir / "venv" / ("Scripts" if (sandbox_dir / "venv" / "Scripts").exists() else "bin") / "python"
        if (sandbox_dir / "requirements.txt").exists():
            subprocess.run([str(pip), "install", "-r", str(sandbox_dir / "requirements.txt")], check=True, cwd=sandbox_dir)
        subprocess.run([str(py), str(sandbox_dir / "experiment.py")], check=True, cwd=sandbox_dir, timeout=900)
    except subprocess.CalledProcessError as e:
        return {"status": "blocked", "reason": "experiment crashed in sandbox", "stderr": str(e)}
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "reason": "experiment exceeded 900s in sandbox"}

    # Compare sandbox results to claimed
    sandbox_results = sandbox_dir / "results.csv"
    if not sandbox_results.exists():
        return {"status": "blocked", "reason": "sandbox did not produce results.csv"}

    df_claim = pd.read_csv(claimed_results)
    df_sandbox = pd.read_csv(sandbox_results)
    mismatches = []
    if list(df_claim.columns) != list(df_sandbox.columns):
        return {"status": "blocked", "reason": "column schemas differ"}
    for col in df_claim.select_dtypes("number").columns:
        for i, (a, b) in enumerate(zip(df_claim[col], df_sandbox[col])):
            if abs(a - b) > 1e-3 and abs(a - b) / max(abs(b), 1e-9) > 0.01:
                mismatches.append({"row": i, "column": col, "claim": a, "sandbox": b})
    return {"status": "ok" if not mismatches else "warned", "mismatches": mismatches}
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/reproducibility_audit.py tests/net_new/test_reproducibility_audit.py
git commit -m "feat(B4): §5.6 reproducibility audit — fresh-venv replay + numerical compare"
```

## Task 6: Hook scaffolding for Blocks 9 / 10 / 11

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/hooks/webui_events.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/hooks/ide_protocol.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/hooks/preprint_submit.py`

- [ ] **Step 1: webui_events.py (SSE emitter)**

```python
# plugins/vedix/mcp/lib/orchestrator/hooks/webui_events.py
"""SSE event emitter for the web UI (Block 9)."""
from __future__ import annotations
import json
import time
from collections import deque
from typing import Iterator

class EventBus:
    def __init__(self, max_buffer: int = 10_000):
        self._events = deque(maxlen=max_buffer)
        self._next_id = 0

    def emit(self, *, kind: str, payload: dict) -> int:
        event = {"id": self._next_id, "ts": time.time(), "kind": kind, "payload": payload}
        self._events.append(event)
        self._next_id += 1
        return event["id"]

    def stream(self, *, since_id: int = 0) -> Iterator[str]:
        for e in self._events:
            if e["id"] > since_id:
                yield f"id: {e['id']}\nevent: {e['kind']}\ndata: {json.dumps(e['payload'])}\n\n"

_BUS = EventBus()

def emit(kind: str, payload: dict) -> int:
    return _BUS.emit(kind=kind, payload=payload)

def stream(since_id: int = 0) -> Iterator[str]:
    return _BUS.stream(since_id=since_id)
```

- [ ] **Step 2: ide_protocol.py (JSON-RPC stub)**

```python
# plugins/vedix/mcp/lib/orchestrator/hooks/ide_protocol.py
"""IDE-plugin JSON-RPC protocol (consumed by VS Code + JetBrains plugins in Block 10)."""
from __future__ import annotations
import json
from dataclasses import dataclass

@dataclass
class IDERequest:
    method: str
    params: dict
    id: int

@dataclass
class IDEResponse:
    result: dict | None
    error: dict | None
    id: int

SUPPORTED_METHODS = {
    "job.new",        # params: ExperimentSetup -> job_id
    "job.status",     # params: {job_id} -> {phase, progress, partial_artifacts}
    "job.cancel",     # params: {job_id} -> {ok}
    "provider.list",  # params: {} -> [{name, region, model}]
    "cost.report",    # params: {since_iso} -> {total_usd, per_provider}
    "manuscript.preview",  # params: {job_id} -> {pdf_url, latex_path}
    "rationale.fetch",     # params: {artifact_path} -> markdown
}

def handle(req: IDERequest) -> IDEResponse:
    if req.method not in SUPPORTED_METHODS:
        return IDEResponse(result=None, error={"code": -32601, "message": f"method {req.method} not supported"}, id=req.id)
    # Stub — Block 10 fills in the per-method handlers
    return IDEResponse(result={"stub": True, "method": req.method, "params": req.params}, error=None, id=req.id)
```

- [ ] **Step 3: preprint_submit.py (CLI scaffolding)**

```python
# plugins/vedix/mcp/lib/orchestrator/hooks/preprint_submit.py
"""Pre-print auto-submission CLI scaffolding (full impl is Block 11)."""
from __future__ import annotations
from pathlib import Path

VALID_TARGETS = {"arxiv", "biorxiv", "osf", "ssrn"}

def submit(*, target: str, manuscript_pdf: Path, metadata: dict, dry_run: bool = True) -> dict:
    if target not in VALID_TARGETS:
        return {"status": "error", "reason": f"unsupported target {target!r}"}
    if not manuscript_pdf.exists():
        return {"status": "error", "reason": f"manuscript PDF not found at {manuscript_pdf}"}
    if dry_run:
        return {"status": "dry-run", "target": target, "would_submit": str(manuscript_pdf)}
    # Block 11 implements per-target API calls
    return {"status": "not_implemented", "note": "use Block 11's full implementation"}
```

- [ ] **Step 4: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/hooks/
git commit -m "feat(B4): scaffolding for §5.7 SSE event bus, §5.8 IDE JSON-RPC, §5.9 pre-print submit"
```

## Block 4 acceptance criteria

- [ ] All `tests/net_new/` tests pass
- [ ] `vedix new --discipline chemistry` triggers preflight dialog and accepts a fully-populated ExperimentSetup
- [ ] After a real experiment runs, `results.csv` audited against manuscript numbers; mismatches surfaced
- [ ] Each major artifact under `~/.vedix/jobs/<id>/` has a `.rationale.md` sibling
- [ ] `vedix run --codebase /path/to/repo` produces a `codebase_summary.json` with file + function counts
- [ ] `vedix audit-reproducibility` end-to-end test on a known-good experiment returns `status: ok`
- [ ] EventBus emits + streams during a full pipeline run
- [ ] Git tag `v3.0.0-block4` pushed
