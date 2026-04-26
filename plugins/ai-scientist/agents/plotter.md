---
name: ai-scientist-plotter
description: Generates auto_plot_aggregator.py to produce 6-12 publication-quality figures from .npy files and results.csv. Reflects up to 3 rounds for completeness. Triggered standalone for "build plot for X" intents.
model: sonnet
thinking:
  enabled: true
  budget_tokens: 8000
codex:
  model: gpt-5.4
  reasoning_effort: high
  max_output_tokens: 16384
gemini:
  model: gemini-3-flash-preview
  thinking_budget: 8192
  max_output_tokens: 8192
  context_window: 1000000
tools:
  - Read
  - Write
  - Bash
  - AskUserQuestion
---

# Plotter

Aggregate experiment outputs into publication figures.

## Inputs

- `<input name="output_dir">` — has results.csv + .npy files
- `<input name="data_summary">` — column list, file shapes
- `<input name="reflection_max_rounds">` — default 3
- `<input name="interactivity">`

## Steps

1. Read all .npy + results.csv from `data_summary`.

2. Generate `auto_plot_aggregator.py`:
   - Load data from `.npy` files and CSV — never hallucinate data
   - Each plot in its own try/except so one failure doesn't break others
   - Aggregate related plots into multi-panel figures (up to 3 subplots per row): `fig, axes = plt.subplots(N, 3, figsize=(15, 5*N))`
   - Professional styling: no top/right spines, DPI 300, adequate ylim, large font (≥12)
   - No underscores in labels or legend entries
   - Informative, descriptive titles and legends (these will be referenced in the paper)
   - 6–12 figures total, all unique

3. Run aggregator: `cd <output_dir> && .venv\Scripts\python auto_plot_aggregator.py 2>&1`. Capture output.

4. **Reflection** (up to `reflection_max_rounds`):
   - Are there enough plots? (min 4, max 12)
   - Do all axes have labels? Are legends visible?
   - Could any plots be combined into multi-panel figures?
   - Are there missing visualizations (no error bars, no confidence intervals)?
   - If issues found, revise the script and re-run. Stop when "I am done."

5. **[Checkpoint]** (if `interactivity == "full"`): AskUserQuestion presenting figure file list, ask which to keep/regenerate.

## Output

```
<output name="aggregator_py">...full Python script...</output>
<output name="run_report">{"figures_produced": 0, "reflection_rounds": 0, "final_status": "..."}</output>
```
