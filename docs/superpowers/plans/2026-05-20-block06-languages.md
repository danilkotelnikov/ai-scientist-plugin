# Block 6 — Languages (7 First-Class) Implementation Plan (§6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Ship 7 languages first-class at v3.0: EN, RU, ES, DE, FR, ZH (Simplified), JA. Each gets a citation backend, LaTeX font stack + Babel/Polyglossia config, register lint, BibTeX preservation rules, and engine routing (`pdflatex` for Latin/Cyrillic; `xelatex` for CJK).

**Architecture:** A `locale/` package with one module per language exposing the same interface (`citation_backend`, `latex_preamble`, `register_lints`, `bib_preserve_rules`, `latex_engine`). A central `locale_router.py` selects the right module given the `--lang` flag. The 23 publisher templates from Block 7 consume the language module's preamble. The register classifiers from Block 5 are already per-language.

**Tech Stack:** `babel` / `polyglossia` LaTeX packages, `gbt7714` for Chinese GB/T 7714, `bibstyle gost-numeric` for Russian, native `pdflatex` + `xelatex` toolchains.

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §6.

---

## File structure

```
plugins/vedix/mcp/lib/orchestrator/locale/
├── __init__.py
├── router.py
├── base.py
├── en.py
├── ru.py
├── es.py
├── de.py
├── fr.py
├── zh.py
├── ja.py
└── register_lints/
    ├── en.py    # carried over from v2.1
    ├── ru.py
    ├── es.py
    ├── de.py
    ├── fr.py
    ├── zh.py
    └── ja.py
```

## Task 1: Locale protocol + router

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/locale/base.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/locale/router.py`
- Test: `tests/locale/test_router.py`

- [ ] **Step 1: Write test**

```python
# tests/locale/test_router.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.locale.router import get_locale

@pytest.mark.parametrize("code,citation_substr,engine", [
    ("en", "biblatex", "pdflatex"),
    ("ru", "gost", "pdflatex"),
    ("zh", "gbt7714", "xelatex"),
    ("ja", "japanese", "xelatex"),
    ("es", "iso-690", "pdflatex"),
    ("de", "din", "pdflatex"),
    ("fr", "nfz44", "pdflatex"),
])
def test_router_returns_correct_locale(code, citation_substr, engine):
    loc = get_locale(code)
    assert loc.code == code
    assert citation_substr.lower() in loc.citation_style.lower()
    assert loc.latex_engine == engine

def test_router_raises_unknown():
    with pytest.raises(KeyError):
        get_locale("ko")
```

- [ ] **Step 2: Implement base + router**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class LocaleConfig:
    code: str                     # ISO 639-1
    name: str                     # human-readable
    citation_style: str           # e.g. "gost-numeric", "biblatex-numeric-comp"
    latex_preamble: str           # \usepackage[...]{...} lines
    bibtex_style: str             # for legacy bibtex; biblatex used by default
    latex_engine: str             # "pdflatex" or "xelatex"
    babel_lang: str               # name passed to \usepackage[..]{babel}
    register_lints: dict          # word/phrase blacklists
    bib_preserve_orthography: bool = True  # keep original script in references
```

```python
# plugins/vedix/mcp/lib/orchestrator/locale/router.py
from .base import LocaleConfig
from . import en, ru, es, de, fr, zh, ja

_LOCALES: dict[str, LocaleConfig] = {
    "en": en.CONFIG, "ru": ru.CONFIG, "es": es.CONFIG, "de": de.CONFIG,
    "fr": fr.CONFIG, "zh": zh.CONFIG, "ja": ja.CONFIG,
}

def get_locale(code: str) -> LocaleConfig:
    if code not in _LOCALES:
        raise KeyError(f"locale {code!r} not supported; available: {sorted(_LOCALES)}")
    return _LOCALES[code]

def list_locales() -> list[str]:
    return sorted(_LOCALES)
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/locale/base.py plugins/vedix/mcp/lib/orchestrator/locale/router.py tests/locale/test_router.py
git commit -m "feat(B6): locale protocol + router"
```

## Task 2: English locale (en.py)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/locale/en.py`

- [ ] **Step 1: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/en.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": [
        "Furthermore", "Moreover", "Additionally", "It is important to note",
        "It is worth mentioning", "Notably", "In conclusion",
    ],
    "blacklist_words": [
        "delve", "intricate", "tapestry", "myriad", "navigate", "underscore",
        "showcase", "leverage", "harness", "robust",
    ],
    "max_em_dashes_per_1000_words": 2,
}

CONFIG = LocaleConfig(
    code="en",
    name="English",
    citation_style="biblatex-numeric-comp",
    latex_preamble=r"""
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[english]{babel}
\usepackage[backend=biber,style=numeric-comp]{biblatex}
""".strip(),
    bibtex_style="ieeetr",
    latex_engine="pdflatex",
    babel_lang="english",
    register_lints=LINTS,
)
```

- [ ] **Step 2: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/locale/en.py
git commit -m "feat(B6): English locale config"
```

## Task 3: Russian locale (ru.py) with ГОСТ-7.0.5

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/locale/ru.py`

- [ ] **Step 1: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/ru.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": [
        "Кроме того", "Более того", "Также", "Стоит отметить",
        "Важно подчеркнуть", "Следует отметить", "Необходимо",
    ],
    "blacklist_words": ["погружаться", "сложный гобелен", "множество", "ориентироваться"],
    "max_em_dashes_per_1000_words": 4,  # Russian uses dashes more than English
    "passive_voice_preference": True,    # preferred academic register in RU
}

CONFIG = LocaleConfig(
    code="ru",
    name="Russian",
    citation_style="gost-numeric",
    latex_preamble=r"""
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}
\usepackage[english,russian]{babel}
\usepackage{noto}
\usepackage[
    backend=biber,
    style=gost-numeric,
    sorting=ntvy,
    language=russian,
    autolang=other
]{biblatex}
""".strip(),
    bibtex_style="gost71s",
    latex_engine="pdflatex",
    babel_lang="russian",
    register_lints=LINTS,
)
```

- [ ] **Step 2: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/locale/ru.py
git commit -m "feat(B6): Russian locale config with ГОСТ-7.0.5"
```

## Task 4-7: Spanish, German, French, Chinese, Japanese locales

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/locale/{es,de,fr,zh,ja}.py`

- [ ] **Step 1: Implement Spanish (es.py)**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/es.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": [
        "Es importante destacar", "Cabe señalar", "Es decir", "En este sentido",
        "Por lo tanto", "Asimismo",
    ],
    "blacklist_words": ["fundamental", "crucial", "imprescindible"],
    "max_em_dashes_per_1000_words": 3,
}

CONFIG = LocaleConfig(
    code="es",
    name="Spanish",
    citation_style="biblatex-iso-690-2",
    latex_preamble=r"""
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[spanish]{babel}
\usepackage[backend=biber,style=iso-numeric]{biblatex}
""".strip(),
    bibtex_style="iso690-numeric-en",
    latex_engine="pdflatex",
    babel_lang="spanish",
    register_lints=LINTS,
)
```

- [ ] **Step 2: Implement German (de.py)**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/de.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": [
        "Hierbei", "Hingegen", "Darüber hinaus", "Folglich",
        "Es ist wichtig zu betonen", "Bekanntlich",
    ],
    "blacklist_words": ["umfassend", "weitreichend", "tiefgreifend"],
    "max_em_dashes_per_1000_words": 2,
    "max_nominalization_rate": 0.30,  # German tends to over-nominalize; cap it
}

CONFIG = LocaleConfig(
    code="de",
    name="German",
    citation_style="biblatex-din-1505-2",
    latex_preamble=r"""
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[ngerman]{babel}
\usepackage[backend=biber,style=numeric-comp,sortlocale=de_DE]{biblatex}
""".strip(),
    bibtex_style="din1505-numeric",
    latex_engine="pdflatex",
    babel_lang="ngerman",
    register_lints=LINTS,
)
```

- [ ] **Step 3: Implement French (fr.py)**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/fr.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": [
        "Il est à noter que", "Il convient de souligner",
        "En effet", "Par ailleurs", "De plus", "À cet égard",
    ],
    "blacklist_words": ["primordial", "essentiel", "fondamental"],
    "max_em_dashes_per_1000_words": 3,
}

CONFIG = LocaleConfig(
    code="fr",
    name="French",
    citation_style="biblatex-nf-z44-005",
    latex_preamble=r"""
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[french]{babel}
\usepackage[backend=biber,style=numeric-comp]{biblatex}
""".strip(),
    bibtex_style="francais",
    latex_engine="pdflatex",
    babel_lang="french",
    register_lints=LINTS,
)
```

- [ ] **Step 4: Implement Simplified Chinese (zh.py)**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/zh.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": ["综上所述", "总而言之", "由此可见", "值得注意的是"],
    "blacklist_phrases": ["不仅...而且", "在...的过程中", "通过...的方式"],
    "max_em_dashes_per_1000_words": 5,  # CJK uses dashes more liberally
}

CONFIG = LocaleConfig(
    code="zh",
    name="Chinese (Simplified)",
    citation_style="gbt7714-2015",
    latex_preamble=r"""
\usepackage{ctex}
\usepackage{fontspec}
\setCJKmainfont{Source Han Serif SC}
\usepackage{gbt7714}
\bibliographystyle{gbt7714-numerical}
""".strip(),
    bibtex_style="gbt7714-numerical",
    latex_engine="xelatex",
    babel_lang="chinese-simplified",
    register_lints=LINTS,
)
```

- [ ] **Step 5: Implement Japanese (ja.py)**

```python
# plugins/vedix/mcp/lib/orchestrator/locale/ja.py
from .base import LocaleConfig

LINTS = {
    "blacklist_paragraph_start": ["なお、", "また、", "そして、", "したがって、"],
    "blacklist_phrases": ["と考えられる", "と思われる", "ものと推測される"],
    "max_em_dashes_per_1000_words": 4,
    "preferred_mode": "常体",  # plain form (vs polite 敬体) — academic register
}

CONFIG = LocaleConfig(
    code="ja",
    name="Japanese",
    citation_style="jis-x-0202",
    latex_preamble=r"""
\usepackage{xeCJK}
\setCJKmainfont{Source Han Serif Japan}
\usepackage[backend=biber,style=numeric-comp]{biblatex}
""".strip(),
    bibtex_style="junsrt",
    latex_engine="xelatex",
    babel_lang="japanese",
    register_lints=LINTS,
)
```

- [ ] **Step 6: Test all locales load + write tests**

```python
# tests/locale/test_all_locales.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.locale.router import get_locale, list_locales

@pytest.mark.parametrize("code", ["en", "ru", "es", "de", "fr", "zh", "ja"])
def test_locale_has_required_fields(code):
    loc = get_locale(code)
    assert loc.code == code
    assert loc.name
    assert loc.citation_style
    assert loc.latex_preamble
    assert loc.latex_engine in ("pdflatex", "xelatex")
    assert loc.babel_lang
    assert loc.register_lints

def test_cjk_languages_use_xelatex():
    for code in ("zh", "ja"):
        assert get_locale(code).latex_engine == "xelatex"

def test_latin_cyrillic_use_pdflatex():
    for code in ("en", "ru", "es", "de", "fr"):
        assert get_locale(code).latex_engine == "pdflatex"

def test_all_locales_listed():
    assert set(list_locales()) == {"en", "ru", "es", "de", "fr", "zh", "ja"}
```

- [ ] **Step 7: Commit**

```bash
pytest tests/locale/ -v
git add plugins/vedix/mcp/lib/orchestrator/locale/ tests/locale/
git commit -m "feat(B6): 7 first-class locales (en, ru, es, de, fr, zh, ja) with citation backends + lints"
```

## Task 5: Wire locale into pipeline (locale-aware engine selection)

**Files:**
- Modify: `plugins/vedix/mcp/lib/orchestrator/pipeline.py` (use locale router)
- Modify: `plugins/vedix/mcp/lib/orchestrator/anti_llm_lint.py` (consume locale lints)

- [ ] **Step 1: Write integration test**

```python
# tests/locale/test_pipeline_locale_wiring.py
from plugins.vedix.mcp.lib.orchestrator.pipeline import Pipeline
from pathlib import Path

def test_pipeline_picks_xelatex_for_chinese(tmp_path):
    p = Pipeline(workspace=tmp_path, language="zh")
    assert p.latex_engine == "xelatex"

def test_pipeline_picks_pdflatex_for_russian(tmp_path):
    p = Pipeline(workspace=tmp_path, language="ru")
    assert p.latex_engine == "pdflatex"

def test_anti_llmish_lint_uses_locale_blacklist(tmp_path):
    from plugins.vedix.mcp.lib.orchestrator.anti_llm_lint import lint_paragraph
    flagged = lint_paragraph("Кроме того, это работа.", language="ru")
    assert flagged["violations"]
```

- [ ] **Step 2: Update pipeline.py**

```python
# plugins/vedix/mcp/lib/orchestrator/pipeline.py (additions)
from .locale.router import get_locale

class Pipeline:
    def __init__(self, *, workspace, language="en", **kwargs):
        self.workspace = workspace
        self.language = language
        self.locale = get_locale(language)
        self.latex_engine = self.locale.latex_engine
        # ... existing initialization
```

- [ ] **Step 3: Update anti_llm_lint.py**

```python
# plugins/vedix/mcp/lib/orchestrator/anti_llm_lint.py (additions)
from .locale.router import get_locale

def lint_paragraph(text: str, *, language: str = "en") -> dict:
    locale = get_locale(language)
    lints = locale.register_lints
    violations = []
    for word in lints.get("blacklist_words", []):
        if word.lower() in text.lower():
            violations.append({"type": "blacklist_word", "term": word})
    for prefix in lints.get("blacklist_paragraph_start", []):
        if text.strip().startswith(prefix):
            violations.append({"type": "paragraph_start", "term": prefix})
    em_dashes = text.count("—")
    n_words = max(1, len(text.split()))
    if em_dashes / n_words * 1000 > lints.get("max_em_dashes_per_1000_words", 2):
        violations.append({"type": "em_dash_overuse", "count": em_dashes})
    return {"violations": violations, "language": language}
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/locale/test_pipeline_locale_wiring.py -v
git add plugins/vedix/mcp/lib/orchestrator/pipeline.py plugins/vedix/mcp/lib/orchestrator/anti_llm_lint.py tests/locale/test_pipeline_locale_wiring.py
git commit -m "feat(B6): wire locale into pipeline + anti-LLMish lint"
```

## Block 6 acceptance criteria

- [ ] All 7 locale modules export valid `LocaleConfig`
- [ ] Router selects the right locale + correct engine (pdflatex vs xelatex)
- [ ] Pipeline auto-picks the right engine per `--lang` flag
- [ ] Anti-LLMish lint uses per-language blacklist (RU lint flags «Кроме того», EN lint flags "Furthermore", etc.)
- [ ] End-to-end smoke: `/vedix new --lang zh "量子算法在...." --venue preprint` compiles via XeLaTeX
- [ ] All `tests/locale/` tests pass
- [ ] Git tag `v3.0.0-block6` pushed
