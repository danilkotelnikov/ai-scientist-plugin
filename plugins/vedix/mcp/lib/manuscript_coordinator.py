"""
Manuscript Assembly Coordinator

Handles:
- Section coordination plan generation
- Consistency checking across sections
- Citation budget management
- Figure/table reference validation
- Final manuscript assembly
"""

import json
import re
from pathlib import Path
from typing import Optional


class ManuscriptCoordinator:
    """Coordinates manuscript section writing for consistency."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.sections = {}
        self.coordination_plan = {}
        self.bibtex_keys = []
        self.figure_refs = []
        self.table_refs = []

    def generate_coordination_plan(self, paper_list: list, experiment_results: str,
                                    hypothesis: str, config: dict) -> dict:
        """Generate a coordination plan for all section subagents."""
        # Extract BibTeX keys
        bib_file = self.output_dir / "references.bib"
        if bib_file.exists():
            with open(bib_file) as f:
                content = f.read()
                self.bibtex_keys = re.findall(r'@.*?\{(\w+),', content)

        # Extract key facts from experiment results
        key_facts = self._extract_key_facts(experiment_results)

        # Generate figure references
        fig_dir = self.output_dir / "figures"
        if fig_dir.exists():
            figures = list(fig_dir.glob("*.png"))
            self.figure_refs = [f"Figure {i+1}: {f.name.replace('.png', '').replace('_', ' ').title()}"
                                for i, f in enumerate(figures[:12])]

        # Generate table references
        csv_file = self.output_dir / "results.csv"
        if csv_file.exists():
            self.table_refs = ["Table 1: Experimental results"]

        # Assign citation budgets per section
        total_refs = len(self.bibtex_keys)
        citation_budget = {
            "Abstract": 0,
            "Introduction": min(8, total_refs // 4),
            "Methods": min(5, total_refs // 6),
            "Results": min(3, total_refs // 8),
            "Discussion": min(10, total_refs // 3),
            "Conclusion": 0
        }

        # Add domain-specific sections
        extra_sections = config.get("extra_sections", [])
        for section in extra_sections:
            citation_budget[section] = min(5, total_refs // 6)

        self.coordination_plan = {
            "citation_budget": citation_budget,
            "shared_facts": key_facts,
            "figure_references": self.figure_refs,
            "table_references": self.table_refs,
            "bibtex_keys": self.bibtex_keys[:30],
            "hypothesis_summary": hypothesis[:200],
            "topic": config.get("topic", ""),
            "domain": config.get("domain", ""),
            "experiment_type": config.get("experiment_type", "")
        }

        return self.coordination_plan

    def assemble_manuscript(self, sections: dict) -> str:
        """Assemble sections into a complete manuscript with consistency checks."""
        self.sections = sections

        # Run consistency checks
        issues = self._check_consistency()

        # Build LaTeX manuscript
        manuscript = self._build_latex(issues)

        return manuscript

    def _check_consistency(self) -> list:
        """Check for consistency issues across sections."""
        issues = []
        all_text = " ".join(self.sections.values())

        # Check for placeholder text
        for placeholder in ["TODO", "XXX", "FIXME", "INSERT"]:
            if placeholder in all_text:
                issues.append(f"Found placeholder text: {placeholder}")

        # Check citation keys exist in .bib
        cited_keys = re.findall(r'\\cite\{([^}]+)\}', all_text)
        for key in cited_keys:
            if key not in self.bibtex_keys:
                issues.append(f"Citation key '{key}' not found in references.bib")

        # Check figure references match actual figures
        fig_refs_in_text = re.findall(r'Figure\s+(\d+)', all_text)
        for ref in fig_refs_in_text:
            if int(ref) > len(self.figure_refs):
                issues.append(f"Figure {ref} referenced but only {len(self.figure_refs)} figures exist")

        # Check for contradictory statements (simple heuristic)
        if "significant" in all_text.lower() and "not significant" in all_text.lower():
            issues.append("Potential contradiction: both 'significant' and 'not significant' mentioned")

        # Check abstract length
        abstract = self.sections.get("Abstract", "")
        if len(abstract.split()) > 300:
            issues.append(f"Abstract too long: {len(abstract.split())} words (max 300)")
        if len(abstract.split()) < 100:
            issues.append(f"Abstract too short: {len(abstract.split())} words (min 100)")

        return issues

    def _build_latex(self, issues: list) -> str:
        """Build complete LaTeX manuscript from sections."""
        # Document preamble
        preamble = r"""\documentclass[10pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{natbib}
\usepackage{caption}
\usepackage{subcaption}

\title{<TITLE>}
\author{AI-Scientist}
\date{\today}

\begin{document}
\maketitle

"""
        # Replace title
        title = self.sections.get("Abstract", "")[:100]
        preamble = preamble.replace("<TITLE>", title)

        # Assemble sections in order
        section_order = [
            "Abstract", "Introduction", "Methods",
            "Related Work", "Experiments", "Statistical Analysis",
            "Structure Prediction", "Machine Learning for Design",
            "Architecture", "Implementation Details", "Benchmarks",
            "Results", "Discussion", "Conclusion"
        ]

        body = ""
        for section_name in section_order:
            if section_name in self.sections:
                content = self.sections[section_name]
                # Ensure section starts with proper LaTeX command
                if section_name == "Abstract":
                    if not content.strip().startswith("\\begin{abstract}"):
                        content = "\\begin{abstract}\n" + content
                    if not content.strip().endswith("\\end{abstract}"):
                        content = content + "\n\\end{abstract}"
                else:
                    if not content.strip().startswith("\\section{"):
                        content = f"\\section{{{section_name}}}\n" + content
                body += content + "\n\n"

        # Add consistency issues as comments
        if issues:
            body += "% Consistency issues found (review before submission):\n"
            for issue in issues:
                body += f"% - {issue}\n"
            body += "\n"

        # Document end
        ending = r"""
\bibliographystyle{plainnat}
\bibliography{references}

\end{document}
"""
        return preamble + body + ending

    def _extract_key_facts(self, experiment_results: str) -> list:
        """Extract key facts from experiment results for shared context."""
        facts = []
        if not experiment_results:
            return facts

        # Look for numeric results
        numbers = re.findall(r'(\d+\.?\d*)\s*[%±/]', experiment_results)
        if numbers:
            facts.append(f"Key metrics: {', '.join(numbers[:5])}")

        # Look for CSV headers
        lines = experiment_results.strip().split("\n")
        if lines:
            facts.append(f"Output format: {lines[0][:100]}")

        return facts[:10]

    def get_subagent_prompt(self, section_name: str) -> str:
        """Generate a prompt for a section subagent with coordination context."""
        plan = self.coordination_plan
        citation_count = plan.get("citation_budget", {}).get(section_name, 3)
        assigned_keys = plan.get("bibtex_keys", [])[:citation_count]

        prompt = f"""You are writing the {section_name} section of a scientific manuscript.

TOPIC: {plan.get('topic', '')}
DOMAIN: {plan.get('domain', '')}
EXPERIMENT TYPE: {plan.get('experiment_type', '')}

HYPOTHESIS: {plan.get('hypothesis_summary', '')}

SHARED FACTS (use these consistently):
{chr(10).join('- ' + f for f in plan.get('shared_facts', []))}

FIGURE REFERENCES (use these exact numbers):
{chr(10).join('- ' + f for f in plan.get('figure_references', []))}

TABLE REFERENCES:
{chr(10).join('- ' + t for t in plan.get('table_references', []))}

AVAILABLE CITATION KEYS (use these for \cite{{key}}):
{', '.join(assigned_keys)}

CITATION BUDGET for this section: {citation_count} citations

RULES:
1. Use ONLY the citation keys listed above
2. Reference figures by their exact numbers
3. Use the shared facts consistently
4. Return ONLY the LaTeX content, starting with the appropriate section command
5. Do NOT include preamble or \end{{document}}
6. Do NOT use placeholder text (TODO, XXX, FIXME)
"""
        return prompt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Manuscript coordination tool")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--plan", action="store_true", help="Generate coordination plan")
    parser.add_argument("--assemble", action="store_true", help="Assemble manuscript from sections")
    args = parser.parse_args()

    coordinator = ManuscriptCoordinator(args.output_dir)

    if args.plan:
        config_file = Path(args.output_dir) / "config.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
        else:
            config = {}

        exp_file = Path(args.output_dir) / "experiment_stdout.txt"
        exp_results = exp_file.read_text() if exp_file.exists() else ""

        hyp_file = Path(args.output_dir) / "hypothesis.md"
        hypothesis = hyp_file.read_text() if hyp_file.exists() else ""

        paper_file = Path(args.output_dir) / "paper_list.json"
        papers = json.loads(paper_file.read_text()) if paper_file.exists() else []

        plan = coordinator.generate_coordination_plan(papers, exp_results, hypothesis, config)
        print(json.dumps(plan, indent=2))
