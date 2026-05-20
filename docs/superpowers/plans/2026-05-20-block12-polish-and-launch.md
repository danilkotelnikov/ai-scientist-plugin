# Block 12 — Polish + Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Final polish + go-live. Docs site (`docs.vedix.ai`), demo videos, end-to-end smoke testing across all hosts (Claude / Codex / Gemini) and all surfaces (CLI plugin / Vedix.ai SaaS / Web UI / VS Code / JetBrains), launch posts on Habr, vc.ru, Hacker News, and Show HN, and the v3.0.0 git tag.

**Architecture:** Docs site is a static MkDocs site under `docs/site/` deployed to Cloudflare Pages. Demo videos recorded with OBS and uploaded to YouTube + embedded in the docs. Smoke testing is a curated 12-script harness that runs every block's acceptance test on real systems. Launch content lives in `docs/launch/` and is timestamped per channel.

**Tech Stack:** MkDocs Material, Cloudflare Pages, OBS Studio for screen recording, `pytest --markers smoke` for the cross-block smoke harness.

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §9 (block B12).

---

## File structure

```
docs/site/
├── mkdocs.yml
├── docs/
│   ├── index.md
│   ├── install.md
│   ├── getting-started.md
│   ├── byok.md
│   ├── languages.md
│   ├── publishers.md
│   ├── rigor-tracks.md
│   ├── training-the-classifier.md
│   ├── saas/
│   │   ├── overview.md
│   │   └── api-reference.md
│   ├── web-ui.md
│   ├── ide-plugins.md
│   ├── preprint-submission.md
│   ├── federated-palace.md
│   └── reference/
│       ├── cli.md
│       └── mcp-tools.md
└── overrides/  (theme overrides)

docs/launch/
├── habr-ru.md                  # Russian long-form post
├── vc-ru.md                    # Russian startup post
├── hn-show-hn.md               # English HN Show post
├── x-twitter-thread.md         # 12-tweet thread
├── arxiv-methods-paper.md      # links to a separate LaTeX project
└── youtube-demo-script.md      # 8-minute demo script

tests/smoke/
├── conftest.py
├── test_block01_bootstrap.py
├── test_block02_byok.py
├── test_block03_rigor.py
├── test_block04_netnew.py
├── test_block05_classifier.py
├── test_block06_languages.py
├── test_block07_publishers.py
├── test_block08_saas.py
├── test_block09_web_ui.py     # Playwright
├── test_block10_ide.py
├── test_block11_collab.py
└── test_end_to_end_pipeline.py  # the integration

scripts/
└── release_v3.sh               # tag + push + publish
```

## Task 1: MkDocs docs site

**Files:**
- Create: `docs/site/mkdocs.yml`
- Create: `docs/site/docs/index.md`
- Create: `docs/site/docs/install.md`
- Create: `docs/site/docs/getting-started.md`

- [ ] **Step 1: mkdocs.yml**

```yaml
site_name: Vedix
site_url: https://docs.vedix.ai/
site_description: Research workbench that turns a topic into a venue-ready manuscript
repo_url: https://github.com/vedix/vedix
edit_uri: edit/master/docs/site/docs/

theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - content.code.copy
    - content.tabs.link
    - search.suggest
    - toc.follow
  palette:
    - scheme: default
      primary: black
      accent: indigo

nav:
  - Home: index.md
  - Install: install.md
  - Getting started: getting-started.md
  - Concepts:
    - BYOK providers: byok.md
    - Languages: languages.md
    - Publisher templates: publishers.md
    - Rigor tracks: rigor-tracks.md
    - Training the classifier: training-the-classifier.md
    - Pre-print submission: preprint-submission.md
    - Federated palace: federated-palace.md
  - Surfaces:
    - Web UI: web-ui.md
    - IDE plugins: ide-plugins.md
    - SaaS overview: saas/overview.md
    - SaaS API reference: saas/api-reference.md
  - Reference:
    - CLI: reference/cli.md
    - MCP tools: reference/mcp-tools.md

markdown_extensions:
  - pymdownx.highlight
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - pymdownx.tasklist
  - admonition
  - tables
  - toc:
      permalink: true
```

- [ ] **Step 2: index.md**

```markdown
# Vedix — research workbench, not a chatbot

Vedix is a single-command research workbench. It turns a topic into a
venue-ready manuscript by running literature search, hypothesis design,
experimentation, claim auditing, and publisher-specific typesetting as one
orchestrated pipeline — with seven rigor mechanisms baked in so the output is
honest before it is polished.

## Install

=== "Linux / macOS"
    ```bash
    curl -fsSL https://vedix.ai/install.sh | bash
    ```

=== "Windows (PowerShell)"
    ```powershell
    iwr -useb https://vedix.ai/install.ps1 | iex
    ```

The bootstrap auto-detects your AI coding assistant (Claude Code, Codex CLI,
Gemini CLI), installs the plugin, registers the 9 MCPs, and fetches the
pre-trained register classifiers (~6 GB; one-time download).

## Run

```
/vedix linear regression on synthetic data
```

That's it. Vedix walks you through a short setup form, runs the pipeline, and
emits a manuscript in your chosen venue's format.

## What's in v3.0

- **23 publisher templates** bundled at install (Nature, Elsevier, Springer,
  Taylor & Francis, Frontiers, Wiley, SAGE, PLOS, Cell, IEEE, ACM, ACS, MDPI,
  RevTeX, RSC, Cambridge, OUP, BMJ, JAMA, ГОСТ-generic, DAN RAS, Uspekhi,
  Overleaf preprint default).
- **7 languages** first-class: English, Russian (ГОСТ-7.0.5), Spanish, German,
  French, Chinese, Japanese.
- **13 BYOK providers**: Anthropic, OpenAI, Google, OpenRouter, Together,
  DeepSeek, Qwen, Moonshot, Zhipu, GigaChat (Sber), YandexGPT, Mistral, Cohere,
  plus self-hosted OpenAI-compatible.
- **7 rigor tracks**: failure-mode learning, citation graph analytics,
  counterfactual citation probing, adversarial multi-pass review, semantic
  revision diff, pre-registration replay, provenance ledger + auto-disclosure.
- **Cross-host**: Claude Code, Codex CLI, Gemini CLI — same skill, same
  pipeline.
- **Vedix.ai SaaS**: hosted job queue, hosted MCPs, web UI, IDE plugins. Free
  tier gets everything; paid tiers buy throughput.

## Open source

Vedix is MIT-licensed. [Repo →](https://github.com/vedix/vedix)
```

- [ ] **Step 3: install.md + getting-started.md (skeletal)**

```markdown
# Install

Linux / macOS:
```bash
curl -fsSL https://vedix.ai/install.sh | bash
```

Windows (PowerShell 5.1+):
```powershell
iwr -useb https://vedix.ai/install.ps1 | iex
```

[interactive host picker output is shown; user can opt which CLI agent gets the plugin]

## Verify

```
> /vedix linear regression on synthetic data
```

If the pipeline runs end-to-end, you're set. Otherwise see [troubleshooting](./troubleshooting.md).
```

```markdown
# Getting started — first job

1. Run `/vedix new` in your AI coding assistant.
2. Fill out the 9-field setup form.
3. Wait ~30 minutes for the pipeline to run.
4. The manuscript appears in your project workspace under `~/.vedix/jobs/<id>/manuscript.pdf`.

[full walkthrough with screenshots; links to `byok`, `languages`, `publishers`]
```

- [ ] **Step 4: Build + deploy**

```bash
cd docs/site
pip install mkdocs-material
mkdocs build  # outputs docs/site/site/
# Deploy to Cloudflare Pages — wire via wrangler or web UI
```

- [ ] **Step 5: Commit**

```bash
git add docs/site/
git commit -m "feat(B12): docs site (MkDocs Material) — index + install + getting-started"
```

## Task 2: Cross-block smoke test harness

**Files:**
- Create: `tests/smoke/conftest.py`
- Create: `tests/smoke/test_end_to_end_pipeline.py`

- [ ] **Step 1: conftest.py**

```python
# tests/smoke/conftest.py
import os
import pytest
from pathlib import Path

def pytest_addoption(parser):
    parser.addoption("--smoke-saas-url", default=os.environ.get("VEDIX_SAAS_URL", "http://localhost:8000"))
    parser.addoption("--smoke-saas-token", default=os.environ.get("VEDIX_SAAS_TOKEN", ""))

@pytest.fixture
def saas_url(request):
    return request.config.getoption("--smoke-saas-url")

@pytest.fixture
def saas_token(request):
    return request.config.getoption("--smoke-saas-token")

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: cross-block end-to-end smoke")
```

- [ ] **Step 2: End-to-end smoke**

```python
# tests/smoke/test_end_to_end_pipeline.py
import os
import time
import httpx
import pytest

@pytest.mark.smoke
def test_full_pipeline_e2e(saas_url, saas_token):
    """Submit a tiny pipeline job to a live SaaS and wait for completion."""
    if not saas_token:
        pytest.skip("VEDIX_SAAS_TOKEN not set; cannot run live smoke")
    headers = {"Authorization": f"Bearer {saas_token}", "Content-Type": "application/json"}
    payload = {
        "topic": "Detecting if x correlates with y in synthetic linear data",
        "discipline": "computer_science", "language": "en", "venue": "preprint",
        "hypothesis_style": "exploratory", "experiment_type": "computational",
        "primary_metric": "pearson_r", "expected_direction": "increase", "tolerance": 0.05,
    }
    with httpx.Client(timeout=60) as client:
        r = client.post(f"{saas_url}/v1/api/jobs", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        job_id = r.json()["job_id"]
        # Poll for completion
        for _ in range(60):  # up to 30 min
            status = client.get(f"{saas_url}/v1/api/jobs/{job_id}", headers=headers).json()
            if status["state"] in ("done", "failed"):
                break
            time.sleep(30)
        assert status["state"] == "done", f"job ended in state {status['state']}"
```

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/
git commit -m "test(B12): cross-block smoke harness — end-to-end on real SaaS"
```

## Task 3: Launch posts (drafts)

**Files:**
- Create: `docs/launch/habr-ru.md`
- Create: `docs/launch/vc-ru.md`
- Create: `docs/launch/hn-show-hn.md`
- Create: `docs/launch/x-twitter-thread.md`
- Create: `docs/launch/youtube-demo-script.md`

- [ ] **Step 1: Write the Habr post (Russian, technical deep-dive)**

```markdown
# Vedix: научный workbench, который не пишет за вас, но не даст ошибиться

(Habr — preview only; full post checked into docs/launch/habr-ru.md after final
sign-off.)

## Проблема

Научные публикации в 2026 году столкнулись с тремя новыми патологиями
эры AI-ассистированного письма:

1. **Коллапс цитирования** — 8–20% ссылок в AI-черновиках сфабрикованы…
2. **Дрейф утверждений** — переписанные предложения инвертируют знаки эффектов
3. **Стилистическое флагирование** — рецензенты замечают AI-маркеры в прозе

Vedix — это workbench, который автоматизирует не написание, а проверку.
[...detailed technical overview with code examples, the seven rigor mechanisms,
benchmarks vs hand-edited drafts...]
```

- [ ] **Step 2: Write the HN Show post (English)**

```markdown
# Show HN: Vedix — cross-host research workbench with seven rigor mechanisms (open-source)

I'm shipping Vedix v3.0 — a research workbench that runs inside Claude Code,
Codex CLI, or Gemini CLI. One command → topic to venue-ready manuscript via
literature search, hypothesis design, experimentation, claim auditing, and
typesetting in 23 publisher formats.

The seven rigor mechanisms catch what AI drafts get wrong:

1. **Failure-mode learning** — HDBSCAN over the pipeline's own failure history
2. **Citation graph analytics** — Gini freshness, density, self-cite ratio
3. **Counterfactual citation probing** — decoy injection + LLM-judge: is the
   citation load-bearing or decorative?
4. **Adversarial multi-pass review** — same reviewer, opposing stances;
   disagreement = robustness signal
5. **Semantic revision diff** — embedding-level claim cosine between revisions
6. **Pre-registration replay** — commit prereg before experiment; audit after
7. **Provenance ledger + auto-disclosure** — per-sentence agent/model tags

13 BYOK providers (Anthropic, OpenAI, Google, OpenRouter, DeepSeek, Qwen,
Moonshot, Zhipu, GigaChat, YandexGPT, Mistral, Cohere, self-hosted). 7
languages first-class. 23 publisher templates bundled.

MIT. https://github.com/vedix/vedix

Vedix.ai is the hosted version — Free tier has every feature; paid tiers buy
throughput.

Looking for: critique on the seven rigor mechanisms, benchmark suggestions,
and integration ideas. Happy to dig into design tradeoffs in comments.
```

- [ ] **Step 3: vc.ru post (RU startup angle)**

```markdown
# Запустили Vedix — научный workbench для русскоязычных учёных

(vc.ru — startup-angle post for the v3.0 launch. Covers the market gap, the
ЮKassa integration, the Russian-first scientific publishing pipeline, ВАК-
perechen' compliance, GigaChat + YandexGPT BYOK support, sanctions-resistant
payment infrastructure. Closes with the tier table.)
```

- [ ] **Step 4: 12-tweet thread**

```markdown
# Twitter / X thread (12 tweets)

1/ I'm shipping Vedix v3.0 — a cross-host research workbench that turns a
   topic into a venue-ready manuscript.

   Open source. BYOK. Runs in Claude Code, Codex CLI, or Gemini CLI.

   The bet: rigor at scale matters more than prose generation.

2/ Seven rigor mechanisms baked into the pipeline:
   • Failure-mode learning
   • Citation graph analytics
   • Counterfactual citation probing
   • Adversarial multi-pass review
   • Semantic revision diff
   • Pre-registration replay
   • Provenance ledger

3-9/ [one rigor mechanism per tweet with a 280-char explanation]

10/ 23 publisher templates bundled. 7 languages first-class
    (en/ru/es/de/fr/zh/ja). 13 BYOK providers including the Chinese
    (DeepSeek, Qwen, Moonshot, Zhipu) and Russian (GigaChat, YandexGPT) ones.

11/ Vedix.ai SaaS: Free tier has every feature. Paid tiers buy throughput.

12/ MIT. https://github.com/vedix/vedix · docs.vedix.ai · vedix.ai
```

- [ ] **Step 5: YouTube demo script**

```markdown
# YouTube demo (8 minutes)

## Outline

00:00 — Cold open: my screen, blank Claude Code session.
00:30 — `/vedix` slash command; setup form appears.
01:00 — Fill out form: discipline=chemistry, language=en, venue=preprint.
01:30 — Pipeline starts. Show literature search phase live.
02:30 — Hypothesis appears + rationale.md companion.
03:00 — Experiment runs. results.csv appears.
03:45 — Numerical audit catches a deliberate 0.92 vs 0.91 mismatch.
04:30 — Manuscript draft renders.
05:00 — Counterfactual probe runs — flags one decorative citation.
05:30 — Adversarial review pass shows steelman + break scores.
06:00 — Provenance ledger panel — every sentence has its source.
06:30 — Switch venue to elsevier:cell-reports-medicine — re-typesets in 90s.
07:00 — AI-disclosure document auto-generated.
07:30 — Push to GitHub. Submit to arXiv via `vedix submit-preprint`.
08:00 — Wrap. Call to action: docs.vedix.ai
```

- [ ] **Step 6: Commit**

```bash
git add docs/launch/
git commit -m "docs(B12): launch posts — Habr, vc.ru, HN, X thread, YouTube script"
```

## Task 4: Release script

**Files:**
- Create: `scripts/release_v3.sh`

- [ ] **Step 1: Write release script**

```bash
# scripts/release_v3.sh
#!/bin/bash
set -euo pipefail

VERSION="3.0.0"

echo "[release] verifying clean working tree…"
test -z "$(git status --porcelain)" || { echo "tree dirty; aborting"; exit 1; }

echo "[release] running cross-block smoke…"
pytest -m smoke tests/smoke/ -v

echo "[release] building docs site…"
( cd docs/site && mkdocs build )

echo "[release] tagging v$VERSION…"
git tag -a "v$VERSION" -m "Vedix v$VERSION — first public release"
git push origin "v$VERSION"

echo "[release] building VS Code extension…"
( cd plugins/vedix/ide/vscode && npm run package )

echo "[release] building JetBrains plugin…"
( cd plugins/vedix/ide/jetbrains && ./gradlew buildPlugin )

echo "[release] publishing pypi…"
( cd plugins/vedix && python -m build && twine upload dist/* )

echo "[release] done. Push announcements: Habr, vc.ru, HN, X."
```

- [ ] **Step 2: Commit**

```bash
chmod +x scripts/release_v3.sh
git add scripts/release_v3.sh
git commit -m "feat(B12): release_v3.sh — orchestrate tag + build + publish"
```

## Task 5: Final smoke test + v3.0.0 tag

- [ ] **Step 1: Full cross-block smoke**

```bash
pytest -m smoke tests/smoke/ -v --tb=short
# Expected: all green; if any block test fails, fix block before tagging
```

- [ ] **Step 2: Build docs**

```bash
( cd docs/site && mkdocs build )
```

- [ ] **Step 3: Tag**

```bash
bash scripts/release_v3.sh
```

- [ ] **Step 4: Post launch content (manual, day-of-launch)**

```bash
# Habr post: paste docs/launch/habr-ru.md content
# vc.ru post: paste docs/launch/vc-ru.md content
# HN Show: paste docs/launch/hn-show-hn.md
# X thread: paste docs/launch/x-twitter-thread.md (one tweet per item)
# YouTube: record + upload per docs/launch/youtube-demo-script.md
```

## Block 12 acceptance criteria

- [ ] `mkdocs build` produces a complete docs site at `docs/site/site/`
- [ ] Cloudflare Pages deploys `docs.vedix.ai` from the build
- [ ] `pytest -m smoke tests/smoke/ -v` passes end-to-end on a live SaaS instance
- [ ] VS Code extension `.vsix` builds; manual install in VS Code works
- [ ] JetBrains plugin `.jar` builds; manual install in IntelliJ works
- [ ] `scripts/release_v3.sh` runs cleanly
- [ ] Git tag `v3.0.0` pushed
- [ ] Launch posts drafted (`docs/launch/`); only timing of publication left
- [ ] First public install (someone outside the team) succeeds
- [ ] Master plan in `docs/superpowers/plans/2026-05-20-00-master-v3-implementation.md` has every block checkbox ticked
