# v3.0 Commercial Rebrand + Monetization (proposal)

**Date:** 2026-04-30
**Status:** proposal — awaiting user decision on the final name + tier structure
**Trigger:** user wants to commercialize `ai-scientist-plugin` after v2.2 ships
**Constraints:** user lives in Russia; payment infrastructure constrained by sanctions; first-class Russian-language support is in v2.2 already

---

## 1. The naming problem

The current name `ai-scientist-plugin` is descriptive but **not brandable**. It also leans on "AI" prominently, which:

- triggers the recent wave of "AI-slop" backlash among academic users
- is generic enough that there's no defensible mark
- limits monetization (no domain, no trademark, no app-store identity)

The new name needs to:

1. **Work in Russian and English** (you live in Russia; first-class RU support is in v2.2). Short enough to render in both Cyrillic and Latin with the same syllabic shape.
2. **Read as a tool for scholars**, not as an AI product. The "AI" should be invisible at the brand layer (it's a *research workbench*; the AI is the engine, not the brand).
3. **Be domain-available** (`.com` ideally; `.ai` / `.so` / `.app` acceptable; `.ru` as the Russian-market mirror).
4. **Have no major trademark conflict** in CS / publishing / academic software.
5. **Be 5–8 characters**, pronounceable in both languages without explanation.

---

## 2. Naming shortlist (12 candidates, ranked)

### Tier A — strongest candidates (recommend picking from this group)

| Name | Latin / Cyrillic | Etymology / vibe | Domain (estimated) | Trademark risk |
|---|---|---|---|---|
| **Knowlex** / Нолекс | knowledge + lex (Latin "law / corpus") | Workbench for the body of knowledge. Reads as serious-but-modern. Pronounceable RU/EN. | `knowlex.com` likely taken (legal SaaS uses it); `knowlex.ai` or `knowlex.so` probably free. | Medium — collides with legal-tech vendor "Knowlex" |
| **Vedix** / Ведикс | Slavic *vědĕti* "to know" + Latin -ix | Indigenous-feeling for Russian users; sounds modern in English. Crisp 5 letters. | `vedix.com` likely free or low-cost; `vedix.ai` definitely free. | Low — no major conflict found |
| **Sapix** / Сапикс | Latin *sapere* "to be wise / to know" + -ix | Same suffix family as Vedix (-ix reads as a software tool). Pan-European etymology. | `sapix.com` may be taken (children's education); `sapix.ai` likely free. | Medium — "Sapix" is a children's tutoring company in Japan |
| **Quaero** / Кверо | Latin "I seek" (etymology of *query*) | Strong scholarly etymology. Used as a brand by an EU search-engine project (now defunct). | `quaero.ai` likely free; `.com` historically owned by the defunct search project | Low — the EU project sunset; mark is unprotected |
| **Verax** / Веракс | Latin *vērāx* "truthful" | One-word brand. Reads as a fact-checker / verifier (matches our DOI-gate + claim-audit pipeline). Strong fit if we lean into rigor. | `verax.com` taken (consultancy); `verax.ai` likely free | Medium — Verax is a name used in fintech compliance |

### Tier B — viable but weaker (only if Tier A is all unavailable)

| Name | Notes |
|---|---|
| **Methodix** / Методикс | "methodology" + -ix. Heavy-handed but unambiguous. Domain risk: medical-research vendor in Switzerland uses it. |
| **Scripta** / Скрипта | Latin "writings". Beautiful but generic; risk of being mistaken for a font / typography product. |
| **Lumen** / Люмен | Latin "light". Overused in software (Lumen Technologies, Laravel Lumen) — high trademark risk. |
| **Inveniō** / Инвенио | Latin "I find". Strong etymology but the macron is hard to type; the EU CERN-affiliated repository platform "Invenio" already exists (open-source library, not a direct competitor but searchable conflict). |
| **Doctix** / Доктикс | "doctor" + -ix. Reads as a medical product; misleading for general research. |
| **Studium** / Студиум | Latin "study / zeal". Solid but a heritage Linux distro / open courseware tools use it. |
| **Cogito** / Когито | "I think" (Descartes). Famous quote → high recognition but also high trademark risk; multiple existing products. |

### Tier C — don't use

`Scientia`, `Scientix` (EU project; STEM education), `Researcho` (try-hard), `Acadex`, `Researchly`, `Lab-something` (too generic).

---

## 3. Naming recommendation

**Primary recommendation: `Vedix` / Ведикс.**

Rationale:
- Slavic *vědĕti* root resonates with Russian users (the user's home market) without sounding parochial in English.
- `-ix` suffix family signals "software tool" globally (Unix, Netflix, Helix).
- Five letters, easy to type, no special characters, no homoglyph attack surface.
- Pronounceable identically in Russian (Ведикс /ˈvʲe.dʲɪks/) and English (/ˈviː.dɪks/).
- Low trademark conflict in our target domains (academic software / SaaS / publishing-tools).
- `vedix.ai` and `vedix.so` likely free; `vedix.com` requires confirmation but is the most likely-available among Tier A.

**Backup: `Knowlex` / Нолекс** — if the user finds Vedix too Slavic-leaning for the global market. Reads as more "corporate-credible" in English but has the legal-tech vendor conflict in `.com`.

**Wildcard: `Verax` / Веракс** — if we lean *hard* into the "rigor / claim verification" angle. Our DOI-gate + typed claim-audit pipeline supports this positioning.

### Action item before v3.0

Run a domain + trademark sweep on the chosen name before any code references it. Tools:

- `whois vedix.com` / `vedix.ai`
- USPTO TESS search for live marks containing "Vedix" in class 9 (software) and class 42 (SaaS)
- Russian Rospatent search (`fips.ru`) for active marks in Russian — the Slavic root means some adjacent words may have local marks
- GitHub org name check: `github.com/vedix` availability
- npm + PyPI: `vedix` package availability

If all clear: register the org, domain, and trademark in parallel.

---

## 4. Product surface (v3.0)

The rebrand changes:

| Surface | v2.x | v3.0 (Vedix) |
|---|---|---|
| Repo | `github.com/danilkotelnikov/ai-scientist-plugin` | `github.com/vedix/vedix` (org) + `vedix-plugin` (CC client) |
| Package | `ai-scientist-plugin` | `vedix` (core) + `vedix-claude` / `vedix-codex` / `vedix-gemini` (clients) |
| MCP namespace | `mcp__ai-scientist__*` | `mcp__vedix__*` |
| CLI command | `/ai-scientist <topic>` | `/vedix <topic>` (or `/research <topic>` — see §6) |
| Domain | none | `vedix.ai` (or `.so`) + `vedix.ru` mirror |
| Docs | repo README + .codex/INSTALL.md | `docs.vedix.ai` (Vercel / Cloudflare Pages) |
| Brand color / mark | none | TBD — propose two: monochrome serif wordmark (academic feel) + a small geometric mark (rotated triangle / open book / corpus sigil) |

Migration: the old `ai-scientist-plugin` repo becomes a deprecation stub for ~6 months redirecting users to the new repo. All v2.x cache paths (`~/.claude/plugins/cache/ai-scientist-plugin/...`) get a one-time migration helper in the new bootstrap that detects them and offers to migrate state to `~/.vedix/`.

---

## 5. Monetization (Russia + global)

### 5.1 Core distribution: free + open-source

The CC client (Claude Code / Codex / Gemini plugin) **stays free + MIT-licensed**. This is non-negotiable:

- Open-source distribution is how the product reaches academic users (the customer base is grad students + postdocs + tenure-track faculty who will not pay for installable plugins).
- The competitive moat is the *trained classifier* + *hosted job queue* + *publisher template engine*, not the dispatcher.
- Open source bypasses Russian payment-infrastructure problems for the entry point.

### 5.2 Paid tier: BYOK SaaS (`vedix.ai`)

Hosted service at `vedix.ai` that adds, on top of the OSS plugin:

| Capability | Plugin (free) | SaaS Pro |
|---|---|---|
| Local Python orchestrator | ✓ | ✓ |
| 9 MCPs via uvx / npx | ✓ | ✓ |
| Trained linguistic classifier | ✗ — retrieval-grounded discriminator only | ✓ — fine-tuned XLM-RoBERTa per discipline + language |
| Per-discipline curated paper corpus (100-300 papers × 8 niches) | ✗ — user-curated | ✓ — vendor-maintained |
| Publisher Word-template engine (ACS, MDPI, Nature, Springer, IEEE, ГОСТ) | ✗ | ✓ |
| Cloud job queue (run jobs without local compute) | ✗ | ✓ |
| Team sharing / shared MemPalace | ✗ | ✓ |
| Citation auto-verification quota (Crossref + Consensus calls) | user's own keys | included in tier |
| Audit-log retention | 7 days local | 90 days cloud |
| Priority model access (GPT-5.5 xhigh, Opus 4.7 64k) | user's key | vendor key + retry |

**BYOK** means: user brings their own Anthropic / OpenAI / Gemini key. We don't markup token costs. We charge for orchestration + hosted features only.

### 5.3 Tier structure (RUB + USD)

| Tier | Price (RUB / mo) | Price (USD / mo) | Limits |
|---|---|---|---|
| **Free** | 0 ₽ | $0 | 100% of plugin features; 0 hosted jobs; BYOK only |
| **Solo** | 1,290 ₽ | $14 | 20 hosted jobs / month; 1 user; trained classifier (RU + EN); publisher templates (5 venues) |
| **Lab** | 4,900 ₽ | $49 | 200 hosted jobs / month; 5 users; full classifier suite; full publisher template library; team shared MemPalace |
| **Institution** | from 24,900 ₽ | from $249 | Unlimited; SSO; on-prem option; SLA |

Pricing benchmarks: ChatGPT Plus 2,490 ₽, Cursor Pro 1,950 ₽, GitHub Copilot 1,000 ₽ — Solo tier at 1,290 ₽ is positioned slightly above Copilot but below ChatGPT Plus, appropriate for a research-specialized tool.

### 5.4 Payment infrastructure for Russia

This is the hardest part. Sanctions-affected payment rails:

| Channel | Russia-resident-friendly? | Notes |
|---|---|---|
| **ЮKassa** (юкасса.ru) | ✓ Best for RUB cards | Yandex-owned, processes Mir + Visa / MC issued by RU banks. Easy KYC for IP individual entrepreneur (ИП) |
| **CloudPayments** | ✓ Alternative | Similar to ЮKassa; slightly more expensive |
| **Boosty / Patreon-RU** | ✓ For recurring subs | Lower friction for small monthly subs; cuts our take 5-10% |
| **Stripe** | ✗ For RU users | Will not process RU-issued cards; works for global customers only |
| **Crypto (USDT TRC-20)** | ✓ Last resort | Highest friction but works regardless of sanctions |

**Recommendation:** ЮKassa for RU customers, Stripe for global. The pricing page detects the user's region from IP and routes accordingly. A monthly subscription in RUB via ЮKassa with auto-renewal is the standard Russian SaaS pattern.

Legal entity options for Russia:
- **ИП (Individual Entrepreneur, "Самозанятый" → ИП-USN-6%)** — simplest, 6% revenue tax, up to 60M ₽/yr revenue cap. Right for ≤ 500-1000 paying subs.
- **ООО** (Limited Liability Company) — if revenue exceeds the ИП cap or institutional contracts require it.

Initial setup: **ИП-USN-6%** registered through Tinkoff (one-day online registration). ЮKassa account opens with that ИП.

### 5.5 Marketing channels (Russian market)

Tier 1 — direct (priority):
- **HSE / MIPT / Skoltech mailing lists** — direct outreach to grad students and postdocs
- **Habr.com** — long-form technical post about the v2.2 release (Russian) showing the cross-host pipeline running with ГОСТ output
- **vc.ru** — startup announcement post for the v3.0 launch
- **Telegram channels:** `@nplusonemag`, `@neural_machine`, `@datasciencegroup`, `@papers_we_love_rus`

Tier 2 — community:
- **Conference workshops:** AINL, AIST, NeurIPS-RU social events
- **University talks:** demo the pipeline in HSE CS faculty seminars, MIPT applied math department, Skoltech CDISE
- **arXiv-search Telegram bots:** become a sponsor / integration partner

Tier 3 — content:
- A 6-part Habr series: "Building an autonomous research pipeline" with technical deep-dives on each subsystem (DOI gate, anti-LLMish lint, Codex spawn_agent waves, etc.)
- A YouTube channel walking through real research jobs end-to-end
- A monthly "Reproducibility audit" post where we run the pipeline on a recently-published Nature paper and surface any claim-vs-figure mismatches

---

## 6. Open questions for the user

Before we lock v3.0:

1. **Name confirmation** — go with `Vedix` (recommended), `Knowlex`, or another from the shortlist?
2. **Slash-command surface** — when invoking from inside Claude Code, do we want `/vedix <topic>` or a more generic `/research <topic>` (so users don't need to remember the brand name to invoke)? The latter is friendlier for casual use; the former is brand-building.
3. **Pricing point for Solo tier** — 1,290 ₽ is the recommendation. Is that right for the Russian academic market, or should it be lower (990 ₽) to match the "below ChatGPT Plus" anchor more tightly?
4. **Free-tier hosted-job allotment** — should Free users get *any* hosted jobs (say 2/month) as a trial, or zero hosted jobs (BYOK only)? Two trial jobs convert better; zero is simpler.
5. **Open-source what's-paid-what's-free boundary** — does the trained classifier get released as a free public model (with the *training data + scripts* paid), or kept entirely behind the paywall? Releasing the model maximizes academic credibility; keeping it paid maximizes ARPU.

Each of these is independently answerable; recommend dropping any blocker into AskUserQuestion when ready to lock.
