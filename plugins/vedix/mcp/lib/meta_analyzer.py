"""
Meta-Analysis & Self-Learning Module

Analyzes patterns across ALL jobs to improve future research:
- Success rates by domain
- Common failure patterns
- What approaches work reliably
- Recommendations for next jobs
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


class MetaAnalyzer:
    """Cross-job meta-analysis for self-learning."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = str(Path.home() / ".ai-scientist")
        self.base_dir = Path(base_dir)

    def run_analysis(self) -> dict:
        """Run full meta-analysis across all jobs."""
        jobs = self._load_jobs()
        trajectories = self._load_trajectories()
        benchmarks = self._load_benchmarks()
        hypotheses = self._load_hypotheses()

        if not jobs:
            return {"error": "No jobs found for analysis"}

        # Compute overall stats
        total = len(jobs)
        successful = sum(1 for j in jobs.values() if j.get("phase") == "done")
        failed = sum(1 for j in jobs.values() if j.get("phase") == "failed")

        # Domain stats
        domain_stats = defaultdict(lambda: {
            "total": 0, "successful": 0, "failed": 0,
            "manuscript_words": [], "papers_found": [],
            "exit_codes": [], "fix_attempts": []
        })

        for job_id, job in jobs.items():
            domain = job.get("domain_template", "unknown")
            domain_stats[domain]["total"] += 1

            if job.get("phase") == "done":
                domain_stats[domain]["successful"] += 1
            elif job.get("phase") == "failed":
                domain_stats[domain]["failed"] += 1

        # Enrich domain stats from trajectories
        for traj in trajectories:
            domain = traj.get("domain", "unknown")
            if traj.get("phase") == "writing":
                wc = traj.get("word_count", 0)
                domain_stats[domain]["manuscript_words"].append(wc)
            if traj.get("phase") == "literature":
                pf = traj.get("papers_found", 0)
                domain_stats[domain]["papers_found"].append(pf)

        # Enrich from benchmarks
        for bench in benchmarks:
            source_job = bench.get("source_job", "")
            job = jobs.get(source_job, {})
            domain = job.get("domain_template", "unknown")
            exit_code = bench.get("metadata", {}).get("exit_code", -1)
            domain_stats[domain]["exit_codes"].append(exit_code)
            domain_stats[domain]["fix_attempts"].append(
                bench.get("metadata", {}).get("fix_attempts", 0)
            )

        # Convert defaultdict to regular dict with computed fields
        domain_stats_clean = {}
        for domain, stats in domain_stats.items():
            words = stats["manuscript_words"]
            papers = stats["papers_found"]
            exit_codes = stats["exit_codes"]

            domain_stats_clean[domain] = {
                "total": stats["total"],
                "successful": stats["successful"],
                "failed": stats["failed"],
                "success_rate": round(stats["successful"] / max(stats["total"], 1), 2),
                "avg_manuscript_words": round(sum(words) / max(len(words), 1)),
                "avg_papers_found": round(sum(papers) / max(len(papers), 1)),
                "experiment_success_rate": round(
                    sum(1 for e in exit_codes if e == 0) / max(len(exit_codes), 1), 2
                ),
                "total_exit_codes": len(exit_codes),
                "common_exit_codes": dict(Counter(exit_codes).most_common(5))
            }

        # Identify common experiment errors
        error_patterns = self._extract_error_patterns(benchmarks, trajectories)

        # Extract successful patterns
        successful_patterns = self._extract_successful_patterns(jobs, trajectories)

        # Generate recommendations
        recommendations = self._generate_recommendations(domain_stats_clean, error_patterns)

        meta = {
            "total_jobs": total,
            "successful_jobs": successful,
            "failed_jobs": failed,
            "overall_success_rate": round(successful / max(total, 1), 2),
            "avg_manuscript_words": round(
                sum(j.get("elapsed_seconds", 0) for j in jobs.values()) / max(total, 1)
            ),
            "domain_stats": domain_stats_clean,
            "common_experiment_errors": error_patterns,
            "successful_experiment_patterns": successful_patterns,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

        return meta

    def generate_what_works(self, meta: dict) -> dict:
        """Generate actionable what-works recommendations."""
        domain_stats = meta.get("domain_stats", {})
        errors = meta.get("common_experiment_errors", [])

        recommendations = {}
        for domain, stats in domain_stats.items():
            success_rate = stats.get("experiment_success_rate", 0)
            common_errors = stats.get("common_exit_codes", {})

            reliable = []
            failures = []

            if success_rate > 0.5:
                reliable.append("experiments generally succeed in this domain")

            # Check for specific error patterns
            if common_errors.get(1, 0) > 0:
                failures.append("experiments often fail with exit code 1")
                if domain == "computational_biology":
                    reliable.append("use synthetic data instead of NCBI API calls")
                    failures.append("biopython Entrez API calls are unreliable")
                if domain == "statistical":
                    reliable.append("ensure all packages in requirements.txt")
                    failures.append("missing packages (pingouin, networkx)")

            recommendations[domain] = {
                "experiment_success_rate": success_rate,
                "avg_manuscript_words": stats.get("avg_manuscript_words", 0),
                "reliable_approaches": reliable if reliable else ["no reliable patterns identified yet"],
                "common_failures": failures if failures else ["no common failures identified"],
            }

        return {
            "successful_patterns": recommendations,
            "recommendations_for_next_job": self._format_recommendations(recommendations, errors),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def _load_jobs(self) -> dict:
        jobs_file = self.base_dir / "jobs.json"
        if not jobs_file.exists():
            return {}
        with open(jobs_file) as f:
            return json.load(f)

    def _load_trajectories(self) -> list:
        traj_file = self.base_dir / "trajectories.jsonl"
        if not traj_file.exists():
            return []
        entries = []
        with open(traj_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _load_benchmarks(self) -> list:
        bench_file = self.base_dir / "knowledge" / "benchmarks.jsonl"
        if not bench_file.exists():
            return []
        entries = []
        with open(bench_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _load_hypotheses(self) -> list:
        hyp_file = self.base_dir / "knowledge" / "hypotheses.jsonl"
        if not hyp_file.exists():
            return []
        entries = []
        with open(hyp_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _extract_error_patterns(self, benchmarks: list, trajectories: list) -> list:
        """Extract common error patterns from failures."""
        patterns = []
        error_counter = Counter()

        for bench in benchmarks:
            content = bench.get("content", "").lower()
            metadata = bench.get("metadata", {})
            exit_code = metadata.get("exit_code", -1)

            if exit_code != 0:
                if "module not found" in content or "import" in content:
                    error_counter["missing_dependency"] += 1
                elif "timeout" in content:
                    error_counter["timeout"] += 1
                elif "network" in content or "connection" in content:
                    error_counter["network_error"] += 1
                elif "file not found" in content:
                    error_counter["file_not_found"] += 1
                else:
                    error_counter["runtime_error"] += 1

        for error_type, count in error_counter.most_common():
            patterns.append({
                "error_type": error_type,
                "count": count,
                "recommendation": self._get_error_recommendation(error_type)
            })

        return patterns

    def _extract_successful_patterns(self, jobs: dict, trajectories: list) -> list:
        """Extract what works from successful jobs."""
        patterns = []
        successful_jobs = {jid: j for jid, j in jobs.items() if j.get("phase") == "done"}

        for job_id, job in successful_jobs.items():
            domain = job.get("domain_template", "unknown")
            topic = job.get("topic", "")[:100]

            # Find related trajectories
            job_trajs = [t for t in trajectories if t.get("job_id") == job_id]
            papers_found = 0
            manuscript_words = 0
            for t in job_trajs:
                if t.get("phase") == "literature":
                    papers_found = t.get("papers_found", 0)
                if t.get("phase") == "writing":
                    manuscript_words = t.get("word_count", 0)

            patterns.append({
                "job_id": job_id,
                "domain": domain,
                "topic": topic,
                "papers_found": papers_found,
                "manuscript_words": manuscript_words,
                "elapsed_seconds": job.get("elapsed_seconds", 0)
            })

        return patterns

    def _generate_recommendations(self, domain_stats: dict, errors: list) -> list:
        """Generate actionable recommendations."""
        recs = []

        for domain, stats in domain_stats.items():
            if stats.get("experiment_success_rate", 0) < 0.5:
                recs.append(
                    f"For {domain}: experiments have {stats['experiment_success_rate']*100:.0f}% "
                    f"success rate. Prefer synthetic/self-contained data over network-dependent data."
                )

        for error in errors:
            if error["count"] > 2:
                recs.append(
                    f"Common error '{error['error_type']}' ({error['count']} occurrences): "
                    f"{error['recommendation']}"
                )

        if not recs:
            recs.append("No strong patterns identified yet — continue collecting data.")

        return recs

    def _get_error_recommendation(self, error_type: str) -> str:
        """Get recommendation for a specific error type."""
        recommendations = {
            "missing_dependency": "Ensure all imports are listed in requirements.txt",
            "timeout": "Simplify experiments or increase timeout; prefer smaller datasets",
            "network_error": "Avoid network API calls in experiments; use synthetic data",
            "file_not_found": "Ensure all file paths are relative to output directory",
            "runtime_error": "Add try/except blocks around main computation"
        }
        return recommendations.get(error_type, "Review experiment code for issues")

    def _format_recommendations(self, recommendations: dict, errors: list) -> list:
        """Format recommendations as a list of strings."""
        recs = []
        for domain, info in recommendations.items():
            if info.get("common_failures"):
                for failure in info["common_failures"]:
                    recs.append(f"For {domain}: avoid {failure}")
            if info.get("reliable_approaches"):
                for approach in info["reliable_approaches"]:
                    recs.append(f"For {domain}: prefer {approach}")
        return recs if recs else ["No specific recommendations yet"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run meta-analysis on AI-Scientist jobs")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    analyzer = MetaAnalyzer()
    meta = analyzer.run_analysis()
    what_works = analyzer.generate_what_works(meta)

    output = {
        "meta_analysis": meta,
        "what_works": what_works
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Meta-analysis written to {args.output}")
    else:
        print(json.dumps(output, indent=2))
