# Install Vedix v3.0 in Claude Code

End-to-end setup from a fresh Claude Code session. Tested on Windows 11
+ PowerShell 7. Linux / macOS notes inline.

## 0. Prerequisites

- **Claude Code** ≥ 1.0 (any host channel)
- **Python 3.11+** on `PATH`
- **Node 20+** (for the bundled MCP servers fetched via `npx`)
- **Git**
- **`uv` / `uvx`** — `pip install --user uv` or `winget install astral-sh.uv`
- **NVIDIA GPU + CUDA driver** (optional; only for the Layer B classifier
  GPU training path)
- **`pdflatex` + `xelatex`** (MiKTeX on Windows, TeX Live on Linux/macOS)
  for PDF generation. Without these the pipeline still emits LaTeX
  sources; you just can't render to PDF locally.

## 1. Clone the repo

**Windows (PowerShell):**

```powershell
mkdir "$HOME\.vedix" -Force
git clone https://github.com/danilkotelnikov/vedix "$HOME\.vedix\repo"
```

**Linux / macOS:**

```bash
mkdir -p "$HOME/.vedix"
git clone https://github.com/danilkotelnikov/vedix "$HOME/.vedix/repo"
```

## 2. Install Python dependencies

```powershell
# Windows
python -m pip install -r "$HOME\.vedix\repo\plugins\vedix\mcp\requirements.txt"
```

```bash
# Linux / macOS
python -m pip install -r "$HOME/.vedix/repo/plugins/vedix/mcp/requirements.txt"
```

For GPU training (RTX 4060 8 GB or similar), make sure you have the
**CUDA-enabled torch wheel**, not the CPU-only one. If
`python -c "import torch; print(torch.cuda.is_available())"` prints `False`
on a machine that has an NVIDIA GPU:

```powershell
pip uninstall -y torch
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu124
# (or cu128 for very recent PyTorch builds)
```

## 3. Register the plugin with Claude Code

Claude Code reads MCP server registrations from `~/.claude.json`. Add (or
merge) the following `mcpServers` block.

**Windows:** `%USERPROFILE%\.claude.json`
**Linux / macOS:** `~/.claude.json`

```jsonc
{
  "mcpServers": {
    "vedix": {
      "command": "python",
      "args": [
        "${env:USERPROFILE}/.vedix/repo/plugins/vedix/mcp/server.py",
        "--mode",
        "stdio"
      ],
      "env": {
        "VEDIX_HOME": "${env:USERPROFILE}/.vedix",
        "PYTHONPATH": "${env:USERPROFILE}/.vedix/repo/plugins/vedix/mcp/lib"
      }
    },

    "mempalace":  { "command": "mempalace-mcp",
                    "env": {"MEMPALACE_ROOT": "${env:USERPROFILE}/.vedix/palace"} },
    "openalex":   { "command": "uvx",
                    "args": ["--from", "git+https://github.com/drAbreu/alex-mcp.git@4.1.0", "alex-mcp"],
                    "env":  {"OPENALEX_MAILTO": "${env:OPENALEX_EMAIL}", "OPENALEX_RATE_PER_SEC": "10"} },
    "semanticscholar": { "command": "python",
                         "args": ["${env:USERPROFILE}/.vedix/external/semanticscholar-MCP-Server/semantic_scholar_server.py"],
                         "env":  {"SEMANTIC_SCHOLAR_API_KEY": "${env:SEMANTIC_SCHOLAR_KEY}"} },
    "arxiv":      { "command": "uvx", "args": ["arxiv-mcp-server"] },
    "biorxiv":    { "command": "python",
                    "args": ["${env:USERPROFILE}/.vedix/external/bioRxiv-MCP-Server/biorxiv_server.py"] },
    "pubmed":     { "command": "npx", "args": ["-y", "pubmed-mcp"] },
    "annas-mcp":  { "command": "npx", "args": ["-y", "annas-mcp", "mcp"],
                    "env":  {"ANNAS_BASE_URL": "https://annas-archive.org",
                             "ANNAS_DOWNLOAD_PATH": "${env:USERPROFILE}/.vedix/raw_downloads",
                             "ANNAS_SECRET_KEY": "${env:ANNAS_SECRET_KEY}"} },
    "fetcher":    { "command": "npx", "args": ["-y", "fetcher-mcp"] }
  }
}
```

If you already have other MCP servers in `~/.claude.json`, merge the
`vedix` + 8 other entries into the existing `mcpServers` object — do not
overwrite the whole file.

## 4. Set required environment variables

Set these in your shell profile (PowerShell `$PROFILE`, bash/zsh
`.zshrc`/`.bashrc`) so they're inherited by Claude Code:

```powershell
# Windows PowerShell
[Environment]::SetEnvironmentVariable("OPENALEX_EMAIL", "you@example.com", "User")
[Environment]::SetEnvironmentVariable("SEMANTIC_SCHOLAR_KEY", "<your key>", "User")
[Environment]::SetEnvironmentVariable("ANNAS_SECRET_KEY", "<your Anna's Archive secret>", "User")
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "<your Anthropic key>", "User")
```

```bash
# Linux / macOS
export OPENALEX_EMAIL="you@example.com"
export SEMANTIC_SCHOLAR_KEY="<your key>"
export ANNAS_SECRET_KEY="<your Anna's Archive secret>"
export ANTHROPIC_API_KEY="<your Anthropic key>"
```

Anna's Archive secret keys are issued per-account and respect a **100
papers/day** download quota. If you don't have one, Vedix still works
against OpenAlex / Semantic Scholar / arXiv / bioRxiv / PubMed — Anna's
Archive is one source among nine.

## 5. (Optional) Configure BYOK provider chain

If you want to use a different LLM provider than the Claude Code
session's default Anthropic key:

```powershell
python -m vedix provider add anthropic --api-key "<key>"
python -m vedix provider add openai    --api-key "<key>"
python -m vedix provider add gigachat  --credentials "<base64-client:secret>"
python -m vedix provider set-chain anthropic openai gigachat
```

Full list of 14 supported providers in `docs/byok/providers.md`.

## 6. Clone the external MCP servers

Two of the registered MCPs (`semanticscholar`, `biorxiv`) need to be
cloned locally because they're not on PyPI / npm:

```powershell
mkdir "$HOME\.vedix\external" -Force
git clone https://github.com/JackKuo666/semanticscholar-MCP-Server "$HOME\.vedix\external\semanticscholar-MCP-Server"
git clone https://github.com/JackKuo666/bioRxiv-MCP-Server          "$HOME\.vedix\external\bioRxiv-MCP-Server"
```

## 7. Restart Claude Code

Close and relaunch. On startup Claude Code reads `~/.claude.json` and
spawns each MCP server. You should see no error popups; if you do,
check `~/.claude/logs/` for which server crashed.

## 8. Verify

In a fresh Claude Code session:

```
> /vedix linear regression on synthetic data
```

If the slash command isn't recognized, the plugin isn't yet wired up —
re-check step 3 (most common cause: `${env:USERPROFILE}` not expanding
in your `.claude.json`; on PowerShell ≤5.1 you may need to write the
literal path instead of the env-var token).

Quick smoke without invoking the full pipeline:

```powershell
python "$HOME\.vedix\repo\plugins\vedix\mcp\server.py" --selftest
```

Expected output: `[selftest] OK — vedix 3.0.0 stdio MCP server ready`.

## 9. (Optional) Prepare the linguistic-register corpus

Vedix's Layer B register classifier (§5.3 of the v3.0 spec) is trained
on a curated per-discipline corpus. To prep the corpus locally:

```powershell
# Tiny smoke run (5 papers per pair, ~5 min)
python "$HOME\.vedix\repo\scripts\prepare_corpus.py" `
    --only-pair chemistry:en `
    --target-count 5 `
    --verbose

# Full corpus build (~12-24h on a workstation; respects Anna's Archive
# 100/day quota per pair)
python "$HOME\.vedix\repo\scripts\prepare_corpus.py" `
    --languages en,ru `
    --disciplines chemistry,biology,medicine,physics,computer_science `
    --target-count 100 `
    --verbose
```

Then train the classifier:

```powershell
# Auto-dispatcher picks GPU (if available, ≥7 GB VRAM) or CPU script
python "$HOME\.vedix\repo\scripts\train_register_classifier.py" `
    --auto `
    --corpus-root "$HOME\.vedix\corpus" `
    --output-root "$HOME\.vedix\classifiers"
```

Training time on RTX 4060 8 GB: ~6-10 hours per (discipline, language)
pair. Heavy job — run as a background process or overnight.

## 10. Run a research pipeline (verbose logging)

In Claude Code:

```
> /vedix research "Effect of solvent polarity on Diels-Alder kinetics" --verbose --discipline chemistry --language en --venue preprint
```

Output lands in `~/.vedix/jobs/<job_id>/`:

```
~/.vedix/jobs/abc12345/
├── manuscript.tex
├── manuscript.pdf
├── references.bib
├── results.csv
├── experiment.py
├── rigor/
│   ├── citation_graph.json
│   ├── counterfactual.json
│   ├── adversarial_review.json
│   ├── provenance.jsonl
│   └── AI_disclosure.md
├── sgca/
│   ├── kg_summary.yaml
│   ├── sentence_ledger.jsonl
│   └── allowed_sets/
└── logs/
    └── orchestrator.log
```

`logs/orchestrator.log` is the verbose stream with every phase
transition, every agent dispatch (which provider chain was used, how
many tokens, how long), every MCP call, every claim verifier decision.

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/vedix` not recognized | `~/.claude.json` not picked up | Restart Claude Code; verify JSON syntax with `python -m json.tool < ~/.claude.json` |
| `npx -y annas-mcp mcp` exits immediately | `ANNAS_SECRET_KEY` missing | Set the env var; restart Claude Code |
| `torch.cuda.is_available() == False` on NVIDIA system | CPU-only torch wheel installed | `pip uninstall torch; pip install torch --index-url https://download.pytorch.org/whl/cu124` |
| `ImportError: No module named anthropic` | Provider SDK not installed | `pip install anthropic` (or whichever) — provider SDKs are optional; only install the ones you use |
| Claude Code crashes on startup after editing `.claude.json` | JSON syntax error | Run `python -m json.tool < ~/.claude.json` to find the parse error |

## 12. Uninstall

```powershell
# Remove the plugin
Remove-Item -Recurse "$HOME\.vedix"
# Then delete the `mcpServers.vedix` (+ 8 others) block from `~/.claude.json` and restart Claude Code.
```

Knowledge stays in `~/.vedix/palace/`. Remove that too if you want a fully clean slate.
