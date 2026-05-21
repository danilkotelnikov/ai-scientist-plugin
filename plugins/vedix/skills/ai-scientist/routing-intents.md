# Routing Intents

The orchestrator's Phase −1 (intent classification) routes a user's natural-language request to one of these 12 named intents using **Claude's reasoning** (not literal regex). The example phrasings below are guidance, not matchers.

When ambiguous, surface `AskUserQuestion` to disambiguate.

## Intent table

| # | Name | Example phrasings | Agents dispatched | Required inputs |
|---|---|---|---|---|
| 1 | review-only | "review X", "peer-review", "critique my paper" | reviewer | path/url to manuscript |
| 2 | analyze-codebase | "analyze codebase", "audit repo Y", "scan code" | codebase-scanner | --codebase path |
| 3 | analyze-data | "analyze results", "stats from results.csv" | plotter, meta-analyst | data path |
| 4 | plot-only | "build plot for", "make figure", "visualize Z" | plotter | data path |
| 5 | literature-only | "find papers", "state of the art", "latest research" | literature-searcher | topic |
| 6 | code-only | "implement X", "write code for", "code Y from scratch" | code-generator (+ experiment-runner if "and run") | spec or topic |
| 7 | hypothesis-only | "hypothesize", "what could explain", "theory for" | ideator, hypothesizer (+ light literature-searcher) | topic |
| 8 | full-pipeline | "research X", "investigate", "study", `/ai-scientist <topic>` | all 12 | topic + domain |
| 9 | compound-lit-code-exp | "look at advanced X and write code, then analyze" | literature-searcher, code-generator, experiment-runner, plotter | topic |
| 10 | comparison | "compare X vs Y experimentally" | code-generator, experiment-runner, plotter, meta-analyst | X, Y |
| 11 | manuscript-from-results | "write paper from <results-dir>" | manuscript-writer, citator, reviewer | results dir |
| 12 | ambiguous | (cannot classify) | none — surface AskUserQuestion | — |

## Disambiguation rules

- If user says "analyze X" with no qualifier and X is a path: prefer **codebase-scanner** if X looks like a repo (presence of `.git`, `package.json`, `pyproject.toml`); else prefer **plotter + meta-analyst** if X is a CSV/JSON/NPY; else ask.
- If user says "review" without a target: ask for the manuscript path.
- If user provides a topic + "and run code": route to compound (literature → codegen → experiment → plot).
- If user provides `/ai-scientist` explicitly OR `--full`: always route to full-pipeline regardless of phrasing.

## Override flags

- `--full` → force full-pipeline (overrides any natural-language intent).
- `--only <agent>` → single-agent mode. Skip all other agents. The agent's required inputs become mandatory CLI flags.
- `--skip <agent1,agent2,...>` → force-skip listed agents in any pipeline.

## Tool minimization

When a partial intent is selected, only the listed agents' tools are active. The orchestrator never grants tool access beyond what the dispatched agents declare in their frontmatter.
