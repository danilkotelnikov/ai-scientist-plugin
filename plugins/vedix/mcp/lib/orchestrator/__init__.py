"""AI-Scientist orchestrator — Python pipeline owning state, retries, convergence,
ensemble aggregation, and checkpoint persistence.

The .md agent files in <PLUGIN>/agents/ are prompt templates filled by this
orchestrator at dispatch time. SKILL.md only handles intent routing and
surfacing AskUserQuestion gates.

See docs/specs/2026-04-27-orchestrator-rewrite-design.md for the architecture.
"""

__version__ = "0.1.0"
