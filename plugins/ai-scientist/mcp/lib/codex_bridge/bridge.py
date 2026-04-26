"""Codex bridge — programmatic delegation + cross-validation.

The bridge wraps the codex-plugin-cc companion script
(${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs) so the ai-scientist
orchestrator can call Codex with strict timeouts, never hang on long
runs, and route Claude failures (API errors, ToS violations) to Codex
as a fallback.

CC-exclusive: detect_host() returns "claude_code" only when running
inside Claude Code. On other hosts the constructor raises
CodexUnavailable.

Threading model:
    - Foreground calls (wait=True) block up to timeout_seconds; on
      timeout the underlying job is cancelled and CodexTimeout raised.
    - Background calls (wait=False) return a job_id; the caller polls
      via status()/result() with its own timeout.
    - All long-running waits use threading.Event so the caller can
      cancel via KeyboardInterrupt without leaving Codex jobs orphaned.

No shell injection: we use shlex.split / list-form subprocess.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# --- Defaults (overridable via settings or constructor kwargs) ---------------
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 5
MAX_RETRIES = 2

# --- Failure-detection heuristics for re-prompt fallback ---------------------
# Strings that suggest Claude couldn't or wouldn't complete the task.
_API_ERROR_PATTERNS = [
    r"API\s+Error",
    r"rate[- ]?limit(ed)?",
    r"\b(429|529|503)\b",
    r"context\s+(window|length)\s+exceeded",
    r"token\s+limit\s+exceeded",
    r"InvalidRequestError",
    r"AnthropicError",
]
_TOS_REFUSAL_PATTERNS = [
    r"I (can't|cannot|won't|will not)\s+help\s+with",
    r"This (request|task)\s+(violates|appears to violate)",
    r"against\s+(my|Anthropic'?s)\s+(usage|content)\s+polic",
    r"unable\s+to\s+(produce|generate|provide)\s+this",
]


def detect_host() -> str:
    """Return the current host: 'claude_code', 'codex', 'gemini', or 'unknown'.

    Heuristics (cheap, no exec):
    - $CLAUDE_CODE_VERSION  or  ~/.claude/  -> claude_code
    - $CODEX_VERSION        or  ~/.codex/   -> codex
    - $GEMINI_VERSION       or  ~/.gemini/  -> gemini
    """
    if os.environ.get("CLAUDE_CODE_VERSION") or Path.home().joinpath(".claude").is_dir():
        return "claude_code"
    if os.environ.get("CODEX_VERSION") or Path.home().joinpath(".codex").is_dir():
        return "codex"
    if os.environ.get("GEMINI_VERSION") or Path.home().joinpath(".gemini").is_dir():
        return "gemini"
    return "unknown"


def looks_like_claude_failure(claude_output: str) -> Optional[str]:
    """Return a short failure-class string if the output looks like Claude
    failed (API error or ToS refusal); else None.

    Used by the SKILL's PostToolUse / fallback flow: if the orchestrator
    sees this, it should re-prompt the same task to Codex.
    """
    if not claude_output:
        return "empty"
    for pat in _API_ERROR_PATTERNS:
        if re.search(pat, claude_output, re.IGNORECASE):
            return "api_error"
    for pat in _TOS_REFUSAL_PATTERNS:
        if re.search(pat, claude_output, re.IGNORECASE):
            return "tos_refusal"
    return None


# --- Exceptions --------------------------------------------------------------
class CodexUnavailable(RuntimeError):
    """codex-plugin-cc isn't installed, isn't authenticated, or we're not on Claude Code."""


class CodexTimeout(RuntimeError):
    """A Codex job exceeded its caller-set timeout. The job was cancelled."""

    def __init__(self, message: str, job_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.job_id = job_id


# --- Result dataclasses ------------------------------------------------------
@dataclass
class CodexResult:
    """Result of a single Codex call (task, review, adversarial-review, result)."""
    job_id: Optional[str]
    status: str  # 'completed', 'cancelled', 'failed', 'timed_out', 'running'
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    parsed: Optional[dict] = None  # if stdout was JSON, the parsed object

    def is_ok(self) -> bool:
        return self.status == "completed" and self.exit_code == 0


@dataclass
class CrossValidation:
    """Result of cross_validate(): Claude's output vs Codex's evaluation."""
    task_type: str
    claude_summary: str
    codex_verdict: str  # 'agree', 'minor_disagree', 'major_disagree', 'codex_error'
    codex_confidence: float  # 0.0–1.0
    discrepancies: list = field(default_factory=list)
    codex_alternative: Optional[str] = None  # if codex disagreed, what it would do instead
    codex_raw: Optional[CodexResult] = None
    requires_user_decision: bool = False  # True when major_disagree


# --- Main bridge -------------------------------------------------------------
class CodexBridge:
    """Programmatic client for codex-plugin-cc.

    Typical usage:
        bridge = CodexBridge(plugin_root="/path/to/codex-plugin/...")
        result = bridge.task("explain my recent commits", wait=True, timeout_seconds=120)
        if result.is_ok():
            print(result.stdout)

    Cross-validation:
        cv = bridge.cross_validate(
            claude_output="...",
            task_inputs={"topic": "...", "domain": "ml"},
            task_type="ideation",
            timeout=180,
        )
        if cv.codex_verdict == "major_disagree":
            # surface to user via AskUserQuestion
            ...

    Fallback:
        try:
            response = some_claude_call(...)
        except ClaudeRefusedError:
            response = bridge.re_prompt_on_failure(
                original_prompt=..., failure_reason="tos_refusal"
            )
    """

    def __init__(
        self,
        plugin_root: Optional[str] = None,
        *,
        default_model: str = DEFAULT_MODEL,
        default_effort: str = DEFAULT_EFFORT,
        default_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        palace_path: Optional[str] = None,
        require_claude_code: bool = True,
        node_binary: str = "node",
    ) -> None:
        self.host = detect_host()
        if require_claude_code and self.host != "claude_code":
            raise CodexUnavailable(
                f"Codex bridge is Claude Code-exclusive (current host: {self.host}). "
                "Install codex-plugin-cc only inside Claude Code."
            )

        self.plugin_root = plugin_root or os.environ.get("CODEX_PLUGIN_CC_ROOT") or self._discover_codex_plugin()
        if not self.plugin_root:
            raise CodexUnavailable(
                "codex-plugin-cc not found. Install via Claude Code: "
                "/plugin install codex@openai-codex"
            )

        self.companion_script = Path(self.plugin_root) / "scripts" / "codex-companion.mjs"
        if not self.companion_script.is_file():
            raise CodexUnavailable(f"codex-companion.mjs missing at {self.companion_script}")

        self.node_binary = shutil.which(node_binary) or node_binary
        self.default_model = default_model
        self.default_effort = default_effort
        self.default_timeout_seconds = default_timeout_seconds
        self.palace_path = palace_path

        self._cancel_events: dict = {}  # job_id -> threading.Event for cooperative cancellation

    # --- Discovery --------------------------------------------------------
    @staticmethod
    def _discover_codex_plugin() -> Optional[str]:
        """Look for codex-plugin-cc inside ~/.claude/plugins/."""
        candidates = [
            Path.home() / ".claude" / "plugins" / "cache" / "openai-codex" / "codex",
            Path.home() / ".claude" / "plugins" / "marketplaces" / "openai-codex" / "plugins" / "codex",
        ]
        for base in candidates:
            if base.is_dir():
                # Find any version subdir containing scripts/codex-companion.mjs
                for version_dir in base.iterdir() if base.is_dir() else []:
                    candidate = version_dir / "scripts" / "codex-companion.mjs"
                    if candidate.is_file():
                        return str(version_dir)
                # Or directly under base
                if (base / "scripts" / "codex-companion.mjs").is_file():
                    return str(base)
        return None

    # --- Low-level subprocess invocation ----------------------------------
    def _run_companion(
        self,
        subcommand: str,
        args: list,
        *,
        timeout_seconds: int,
        capture_output: bool = True,
    ) -> CodexResult:
        """Run `node codex-companion.mjs <subcommand> <args>` with hard timeout.

        Cancels the subprocess on timeout and raises CodexTimeout.
        """
        cmd = [self.node_binary, str(self.companion_script), subcommand] + args
        start = time.monotonic()
        # Constructor guarantees self.plugin_root is set (else raised CodexUnavailable).
        plugin_root_str: str = str(self.plugin_root)
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root_str
        try:
            proc = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            # Best-effort cancel of any background job that may have been launched.
            self._best_effort_cancel_orphan_jobs()
            raise CodexTimeout(
                f"Codex {subcommand!r} exceeded timeout={timeout_seconds}s "
                f"(elapsed {duration:.1f}s). Cancelled.",
            ) from exc

        duration = time.monotonic() - start
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        job_id = self._extract_job_id(stdout) or self._extract_job_id(stderr)
        parsed = None
        try:
            parsed = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            pass
        status = "completed" if proc.returncode == 0 else "failed"
        return CodexResult(
            job_id=job_id,
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            duration_seconds=duration,
            parsed=parsed,
        )

    @staticmethod
    def _extract_job_id(text: str) -> Optional[str]:
        if not text:
            return None
        m = re.search(r"\bjob[_ -]?id[:= ]?([\w\-]{6,})", text, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'"job_id"\s*:\s*"([\w\-]+)"', text)
        if m:
            return m.group(1)
        return None

    def _best_effort_cancel_orphan_jobs(self) -> None:
        """If a sync call timed out, the background job may still be running.
        Try to cancel it via the companion script. Never raise; this is cleanup.
        """
        try:
            subprocess.run(
                [self.node_binary, str(self.companion_script), "status", "--json"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            # If there are running jobs we don't track, leave them — the user
            # can /codex:cancel them manually. We only auto-cancel jobs we
            # know we own. (The companion script doesn't expose ownership;
            # this is a safe no-op for now.)
        except Exception:
            pass

    # --- Public API: task -------------------------------------------------
    def task(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        write: bool = False,
        wait: bool = True,
        timeout_seconds: Optional[int] = None,
        resume: bool = False,
    ) -> CodexResult:
        """Submit a task to Codex.

        wait=True (default) blocks until completion or timeout.
        wait=False returns immediately with a job_id; poll via status()/result().
        """
        args = []
        if model:
            args += ["--model", model]
        if effort:
            args += ["--effort", effort]
        if write:
            args += ["--write"]
        if resume:
            args += ["--resume-last"]
        if not wait:
            args += ["--background"]
        else:
            args += ["--wait"]
        args += [prompt]
        return self._run_companion(
            "task", args,
            timeout_seconds=timeout_seconds or self.default_timeout_seconds,
        )

    def task_background(self, prompt: str, **kwargs: Any) -> str:
        """Submit and return job_id immediately (does not block)."""
        kwargs["wait"] = False
        result = self.task(prompt, **kwargs)
        if not result.job_id:
            raise CodexUnavailable(f"task_background: no job_id in stdout: {result.stdout[:200]}")
        return result.job_id

    # --- Public API: review -----------------------------------------------
    def review(
        self,
        *,
        scope: str = "auto",  # auto | working-tree | branch
        base: Optional[str] = None,
        wait: bool = True,
        timeout_seconds: Optional[int] = None,
    ) -> CodexResult:
        args = ["--scope", scope]
        if base:
            args += ["--base", base]
        args += ["--wait"] if wait else ["--background"]
        return self._run_companion(
            "review", args,
            timeout_seconds=timeout_seconds or self.default_timeout_seconds,
        )

    def adversarial_review(
        self,
        *,
        focus: str = "",
        scope: str = "auto",
        base: Optional[str] = None,
        wait: bool = True,
        timeout_seconds: Optional[int] = None,
    ) -> CodexResult:
        args = ["--scope", scope]
        if base:
            args += ["--base", base]
        args += ["--wait"] if wait else ["--background"]
        if focus:
            args += [focus]
        return self._run_companion(
            "adversarial-review", args,
            timeout_seconds=timeout_seconds or self.default_timeout_seconds,
        )

    # --- Public API: status / result / cancel -----------------------------
    def status(self, job_id: Optional[str] = None, *, timeout_ms: Optional[int] = None) -> CodexResult:
        args = []
        if job_id:
            args.append(job_id)
        if timeout_ms:
            args += ["--timeout-ms", str(timeout_ms)]
        args.append("--json")
        return self._run_companion("status", args, timeout_seconds=30)

    def result(self, job_id: str) -> CodexResult:
        return self._run_companion("result", [job_id], timeout_seconds=60)

    def cancel(self, job_id: str) -> bool:
        r = self._run_companion("cancel", [job_id], timeout_seconds=30)
        return r.is_ok()

    # --- Public API: poll until done (with timeout) ----------------------
    def wait_for_completion(
        self,
        job_id: str,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> CodexResult:
        """Poll status() until the job is done or timeout. On timeout, cancel + raise."""
        deadline = time.monotonic() + timeout_seconds
        cancel_event = threading.Event()
        self._cancel_events[job_id] = cancel_event
        try:
            while time.monotonic() < deadline:
                if cancel_event.is_set():
                    self.cancel(job_id)
                    raise CodexTimeout(f"Job {job_id} cancelled by caller", job_id=job_id)
                s = self.status(job_id)
                phase = (s.parsed or {}).get("phase") or (s.parsed or {}).get("status") or ""
                if phase in ("completed", "succeeded", "done"):
                    return self.result(job_id)
                if phase in ("failed", "error", "cancelled"):
                    return CodexResult(
                        job_id=job_id, status=phase, stdout=s.stdout, stderr=s.stderr,
                        exit_code=1, duration_seconds=0.0, parsed=s.parsed,
                    )
                time.sleep(poll_interval_seconds)
            self.cancel(job_id)
            raise CodexTimeout(
                f"Job {job_id} exceeded timeout={timeout_seconds}s. Cancelled.",
                job_id=job_id,
            )
        finally:
            self._cancel_events.pop(job_id, None)

    # --- Public API: cross-validate --------------------------------------
    def cross_validate(
        self,
        claude_output: str,
        task_inputs: dict,
        task_type: str,
        *,
        model: Optional[str] = None,
        effort: str = "high",
        timeout_seconds: int = 300,
    ) -> CrossValidation:
        """Submit Claude's output + the original task inputs to Codex; ask
        Codex to evaluate it.

        task_type drives the evaluation rubric:
          - "ideation"   — is the idea novel, testable, well-scoped?
          - "hypothesis" — does math + methodology hold up?
          - "code"       — does the script implement the spec? bugs? perf?
          - "writing"    — is the manuscript prose clear, accurate, well-cited?
          - "review"     — is the peer-review fair, detailed, well-justified?
          - "search"     — are the literature results on-topic, deduplicated, fresh?

        Returns CrossValidation with verdict (agree / minor_disagree /
        major_disagree / codex_error) and discrepancies list.
        """
        rubric = self._cross_validate_rubric(task_type)
        prompt = (
            f"You are cross-validating another LLM's output for an ai-scientist research pipeline.\n\n"
            f"Task type: {task_type}\n"
            f"Original task inputs:\n```json\n{json.dumps(task_inputs, indent=2, default=str)[:4000]}\n```\n\n"
            f"Claude's output to evaluate:\n```\n{claude_output[:8000]}\n```\n\n"
            f"Evaluation rubric for '{task_type}':\n{rubric}\n\n"
            "Return ONLY a JSON object with this schema, no prose outside it:\n"
            "{\n"
            '  "verdict": "agree" | "minor_disagree" | "major_disagree",\n'
            '  "confidence": 0.0..1.0,\n'
            '  "discrepancies": ["<short bullet>", ...],\n'
            '  "codex_alternative": "<what you would do differently, if anything>"\n'
            "}\n"
        )
        try:
            r = self.task(
                prompt,
                model=model or self.default_model,
                effort=effort,
                wait=True,
                timeout_seconds=timeout_seconds,
                write=False,
            )
        except CodexTimeout:
            return CrossValidation(
                task_type=task_type, claude_summary=claude_output[:200],
                codex_verdict="codex_error", codex_confidence=0.0,
                discrepancies=["Codex cross-validation timed out"],
                codex_alternative=None, codex_raw=None,
                requires_user_decision=False,
            )

        # Parse Codex's JSON response.
        verdict = "codex_error"
        confidence = 0.0
        discrepancies: list = []
        alternative = None
        if r.is_ok():
            json_text = self._extract_json_from(r.stdout)
            try:
                obj = json.loads(json_text)
                verdict = obj.get("verdict", "codex_error")
                confidence = float(obj.get("confidence", 0.0))
                discrepancies = list(obj.get("discrepancies", []))
                alternative = obj.get("codex_alternative")
            except (json.JSONDecodeError, ValueError, TypeError):
                discrepancies = [f"Codex returned non-JSON: {r.stdout[:300]!r}"]

        return CrossValidation(
            task_type=task_type,
            claude_summary=claude_output[:200],
            codex_verdict=verdict,
            codex_confidence=confidence,
            discrepancies=discrepancies,
            codex_alternative=alternative,
            codex_raw=r,
            requires_user_decision=(verdict == "major_disagree"),
        )

    @staticmethod
    def _cross_validate_rubric(task_type: str) -> str:
        rubrics = {
            "ideation": (
                "- Is the idea testable in a small, bounded experiment?\n"
                "- Is the related-work positioning honest (not overclaiming novelty)?\n"
                "- Are the experiments concrete (specific metrics, not vague)?\n"
                "- Are risks acknowledged?"
            ),
            "hypothesis": (
                "- Does the math match the methodology?\n"
                "- Is the statistical framework appropriate (right test, correction, effect size)?\n"
                "- Are dependencies realistic (no missing or mis-named libs)?\n"
                "- Are claims supported by cited literature?"
            ),
            "code": (
                "- Does the code implement the methodology in hypothesis.md?\n"
                "- Are there bugs, off-by-ones, division-by-zero, NaN risks?\n"
                "- Are the imports correct and the dependency list accurate?\n"
                "- Is error handling reasonable (try/except where needed)?\n"
                "- Will this run in <60 seconds on a normal CPU?"
            ),
            "writing": (
                "- Does the manuscript accurately reflect the experiment results?\n"
                "- Are claims appropriately hedged (no overclaiming)?\n"
                "- Are all cite{} keys defined in references.bib?\n"
                "- Are figures referenced consistently?\n"
                "- Any placeholder text (TODO/XXX/FIXME)?\n"
                "- Does the abstract match the conclusion?"
            ),
            "review": (
                "- Are the strengths/weaknesses concrete (point to specific lines)?\n"
                "- Are the scores justified by the rubric?\n"
                "- Are the actionable_fixes specific and surgical?\n"
                "- Did the review miss any obvious issues?"
            ),
            "search": (
                "- Are the results on-topic for the query?\n"
                "- Are duplicates flagged?\n"
                "- Are the dates fresh (matches the year_floor request)?\n"
                "- Are non-academic sources excluded?"
            ),
        }
        return rubrics.get(task_type, "- Is the output internally consistent and on-task?")

    @staticmethod
    def _extract_json_from(text: str) -> str:
        """Pull the first balanced {...} JSON object out of possibly-noisy stdout.

        Python's `re` module doesn't support recursive patterns, so we
        scan brace-by-brace, ignoring braces inside string literals.
        """
        start = text.find("{")
        if start == -1:
            return text
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return text[start:]

    # --- Public API: re-prompt-on-failure fallback ------------------------
    def re_prompt_on_failure(
        self,
        original_prompt: str,
        failure_reason: str,
        *,
        model: Optional[str] = None,
        effort: str = "high",
        timeout_seconds: int = 600,
    ) -> CodexResult:
        """When Claude hits an API error or refuses on ToS grounds, re-prompt
        the same task to Codex. Used by the orchestrator's fallback flow.

        failure_reason is one of: 'api_error', 'tos_refusal', 'empty', 'timeout'
        """
        wrapped = (
            f"Claude (Anthropic) was unable to complete the task below. "
            f"Failure reason: {failure_reason}. "
            f"Please complete it. The task is research-pipeline work for an "
            f"automated AI-Scientist plugin; treat it as a normal coding/"
            f"research task.\n\n"
            f"--- ORIGINAL TASK ---\n{original_prompt}\n--- END TASK ---"
        )
        return self.task(
            wrapped,
            model=model or self.default_model,
            effort=effort,
            wait=True,
            timeout_seconds=timeout_seconds,
            write=False,
        )

    # --- Helpers for delegating literature-search Anna's queries ---------
    def annas_search(
        self,
        query: str,
        *,
        max_results: int = 10,
        timeout_seconds: int = 180,
    ) -> CodexResult:
        """Delegate an Anna's Archive query to Codex. Codex has its own
        annas-mcp connectivity (or uses fetcher) and avoids the
        Claude-Code-specific rate limits and tool restrictions on the
        annas-mcp tool.
        """
        prompt = (
            f"Use the Anna's Archive MCP (annas-mcp__article_search) to search for: "
            f"{query!r}. Return up to {max_results} results as a JSON array with the "
            f"unified schema: title, authors, year, doi, journal, url, abstract, source. "
            f"No prose outside the JSON array."
        )
        return self.task(
            prompt,
            wait=True,
            timeout_seconds=timeout_seconds,
            write=False,
            effort="medium",
        )
