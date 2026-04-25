"""Static checks: every agent file has required frontmatter fields."""
import re
from pathlib import Path

import pytest
import yaml

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = PLUGIN_ROOT / "agents"

EXPECTED_AGENTS = {
    "ideator", "codebase-scanner", "literature-searcher",
    "hypothesizer", "code-generator", "experiment-runner",
    "plotter", "manuscript-writer", "citator", "reviewer",
    "meta-analyst", "fixer",
}

REQUIRED_FRONTMATTER_KEYS = {"name", "description", "model", "thinking", "tools"}
ALLOWED_MODELS = {"opus", "sonnet", "haiku", "inherit"}


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        raise AssertionError(f"{path.name}: no YAML frontmatter")
    return yaml.safe_load(m.group(1))


def test_all_expected_agents_exist():
    found = {p.stem for p in AGENTS_DIR.glob("*.md")}
    missing = EXPECTED_AGENTS - found
    extra = found - EXPECTED_AGENTS
    assert not missing, f"missing agent files: {missing}"
    assert not extra, f"unexpected agent files: {extra}"


@pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
def test_agent_has_required_frontmatter(agent_name):
    fm = parse_frontmatter(AGENTS_DIR / f"{agent_name}.md")
    missing = REQUIRED_FRONTMATTER_KEYS - set(fm.keys())
    assert not missing, f"{agent_name}.md missing frontmatter keys: {missing}"


@pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
def test_agent_model_valid(agent_name):
    fm = parse_frontmatter(AGENTS_DIR / f"{agent_name}.md")
    assert fm["model"] in ALLOWED_MODELS, f"{agent_name}.md: invalid model {fm['model']!r}"


@pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
def test_agent_thinking_block(agent_name):
    fm = parse_frontmatter(AGENTS_DIR / f"{agent_name}.md")
    thinking = fm["thinking"]
    assert isinstance(thinking, dict), f"{agent_name}.md: thinking must be dict"
    assert "enabled" in thinking and "budget_tokens" in thinking, \
        f"{agent_name}.md: thinking needs enabled+budget_tokens"
    assert isinstance(thinking["budget_tokens"], int), \
        f"{agent_name}.md: budget_tokens must be int"
    assert 0 <= thinking["budget_tokens"] <= 128000, \
        f"{agent_name}.md: budget_tokens out of range"


@pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
def test_agent_tools_list(agent_name):
    fm = parse_frontmatter(AGENTS_DIR / f"{agent_name}.md")
    tools = fm["tools"]
    assert isinstance(tools, list) and len(tools) > 0, \
        f"{agent_name}.md: tools must be non-empty list"
