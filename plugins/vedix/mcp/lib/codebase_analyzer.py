"""
Codebase Context Analyzer

Scans an existing codebase to extract architecture, dependencies,
entry points, and extension points for grounding AI-Scientist research.
"""

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional


class CodebaseAnalyzer:
    """Analyzes a codebase to provide context for research grounding."""

    def __init__(self, codebase_path: str):
        self.codebase_path = Path(codebase_path)
        self.modules = []
        self.dependencies = {"runtime": [], "dev": []}
        self.entry_points = []
        self.test_files = []
        self.key_classes = []
        self.key_functions = []
        self.language = "unknown"
        self.framework = "unknown"
        self.extension_points = []

    def analyze(self) -> dict:
        """Run full analysis and return structured results."""
        if not self.codebase_path.exists():
            return {"error": f"Path not found: {self.codebase_path}"}

        self._detect_language()
        self._scan_modules()
        self._scan_dependencies()
        self._find_entry_points()
        self._find_test_files()
        self._extract_key_symbols()
        self._identify_extension_points()

        return {
            "path": str(self.codebase_path),
            "language": self.language,
            "framework": self.framework,
            "total_files": self._count_files(),
            "total_lines": self._count_lines(),
            "modules": self.modules,
            "dependencies": self.dependencies,
            "entry_points": self.entry_points,
            "test_files": self.test_files[:20],
            "key_classes": self.key_classes[:30],
            "key_functions": self.key_functions[:50],
            "extension_points": self.extension_points,
            "key_patterns": self._detect_patterns()
        }

    def _detect_language(self):
        """Detect primary language from file extensions."""
        ext_counts = Counter()
        for ext in ["*.py", "*.js", "*.ts", "*.tsx", "*.rs", "*.go", "*.java", "*.cpp", "*.c"]:
            count = len(list(self.codebase_path.rglob(ext)))
            ext_counts[ext] = count

        if not ext_counts:
            self.language = "unknown"
            return

        primary = ext_counts.most_common(1)[0][0]
        lang_map = {
            "*.py": "python", "*.js": "javascript", "*.ts": "typescript",
            "*.tsx": "typescript", "*.rs": "rust", "*.go": "go",
            "*.java": "java", "*.cpp": "cpp", "*.c": "c"
        }
        self.language = lang_map.get(primary, "unknown")

    def _scan_modules(self):
        """Scan for module structure."""
        if self.language == "python":
            for init_file in self.codebase_path.rglob("__init__.py"):
                module_dir = init_file.parent
                rel_path = module_dir.relative_to(self.codebase_path)
                # Count files in module
                py_files = list(module_dir.rglob("*.py"))
                classes = self._count_classes_in_files(py_files)
                functions = self._count_functions_in_files(py_files)
                self.modules.append({
                    "name": str(rel_path).replace(os.sep, "."),
                    "path": str(rel_path),
                    "files": len(py_files),
                    "classes": classes,
                    "functions": functions
                })

    def _scan_dependencies(self):
        """Scan for dependency declarations."""
        # Python
        req_file = self.codebase_path / "requirements.txt"
        if req_file.exists():
            with open(req_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        pkg = line.split("==")[0].split(">=")[0].split("<")[0].strip()
                        self.dependencies["runtime"].append(pkg)

        setup_file = self.codebase_path / "setup.py"
        if setup_file.exists():
            with open(setup_file) as f:
                content = f.read()
                # Extract install_requires
                match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if match:
                    for dep in re.findall(r'"([^"]+)"|\'([^\']+)\'', match.group(1)):
                        pkg = (dep[0] or dep[1]).split("==")[0].split(">=")[0]
                        self.dependencies["runtime"].append(pkg)

        pyproject = self.codebase_path / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject) as f:
                content = f.read()
                # Simple extraction (not full TOML parsing)
                in_deps = False
                for line in content.split("\n"):
                    if "dependencies" in line and "[" in line:
                        in_deps = True
                        continue
                    if in_deps and "]" in line:
                        in_deps = False
                        continue
                    if in_deps:
                        pkg = line.strip().strip('",').strip()
                        if pkg and not pkg.startswith("#"):
                            self.dependencies["runtime"].append(
                                pkg.split("==")[0].split(">=")[0].split("~=")[0]
                            )

        # JavaScript/TypeScript
        pkg_json = self.codebase_path / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json) as f:
                    pkg_data = json.load(f)
                self.dependencies["runtime"] = list(pkg_data.get("dependencies", {}).keys())
                self.dependencies["dev"] = list(pkg_data.get("devDependencies", {}).keys())
            except json.JSONDecodeError:
                pass

        # Rust
        cargo = self.codebase_path / "Cargo.toml"
        if cargo.exists():
            with open(cargo) as f:
                content = f.read()
                in_deps = False
                for line in content.split("\n"):
                    if "[dependencies]" in line:
                        in_deps = True
                        continue
                    if in_deps and line.startswith("["):
                        in_deps = False
                        continue
                    if in_deps and "=" in line:
                        pkg = line.split("=")[0].strip()
                        self.dependencies["runtime"].append(pkg)

    def _find_entry_points(self):
        """Find main entry points."""
        candidates = [
            "main.py", "app.py", "cli.py", "server.py", "wsgi.py", "asgi.py",
            "index.js", "index.ts", "main.js", "main.ts", "app.js", "app.ts",
            "src/main.py", "src/main.js", "src/main.ts", "src/index.js", "src/index.ts",
            "src/app.py", "src/app.js", "src/app.ts"
        ]
        for candidate in candidates:
            path = self.codebase_path / candidate
            if path.exists():
                self.entry_points.append(str(path.relative_to(self.codebase_path)))

    def _find_test_files(self):
        """Find test files."""
        patterns = ["*test*.py", "test_*", "*_test.py", "*.test.js", "*.test.ts",
                    "*.spec.js", "*.spec.ts", "tests/**/*.py", "test/**/*.py"]
        for pattern in patterns:
            for f in self.codebase_path.rglob(pattern):
                if f.is_file():
                    self.test_files.append(str(f.relative_to(self.codebase_path)))

    def _extract_key_symbols(self):
        """Extract key classes and functions."""
        if self.language == "python":
            for py_file in self.codebase_path.rglob("*.py"):
                if "test" in str(py_file).lower() or "__pycache__" in str(py_file):
                    continue
                try:
                    with open(py_file, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("class ") and "(" in line:
                                class_name = line.split("class ")[1].split("(")[0].strip()
                                self.key_classes.append({
                                    "name": class_name,
                                    "file": str(py_file.relative_to(self.codebase_path))
                                })
                            elif line.startswith("class ") and ":" in line:
                                class_name = line.split("class ")[1].split(":")[0].strip()
                                self.key_classes.append({
                                    "name": class_name,
                                    "file": str(py_file.relative_to(self.codebase_path))
                                })
                            elif line.startswith("def ") and not line.startswith("def _"):
                                func_name = line.split("def ")[1].split("(")[0].strip()
                                if func_name:
                                    self.key_functions.append({
                                        "name": func_name,
                                        "file": str(py_file.relative_to(self.codebase_path))
                                    })
                except (PermissionError, OSError):
                    pass

    def _identify_extension_points(self):
        """Identify where new code could integrate."""
        # Look for TODO/FIXME comments as natural extension points
        for py_file in self.codebase_path.rglob("*.py"):
            if "test" in str(py_file).lower() or "__pycache__" in str(py_file):
                continue
            try:
                with open(py_file, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if any(marker in line for marker in ["TODO", "FIXME", "HACK", "XXX"]):
                            self.extension_points.append({
                                "file": str(py_file.relative_to(self.codebase_path)),
                                "line": i,
                                "marker": line.strip()[:80]
                            })
            except (PermissionError, OSError):
                pass

        # Look for abstract classes / interfaces
        if self.language == "python":
            for py_file in self.codebase_path.rglob("*.py"):
                try:
                    with open(py_file, encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        if "ABC" in content or "abstractmethod" in content:
                            self.extension_points.append({
                                "type": "abstract_class",
                                "file": str(py_file.relative_to(self.codebase_path)),
                                "description": "Contains abstract base classes for extension"
                            })
                except (PermissionError, OSError):
                    pass

    def _detect_patterns(self) -> list:
        """Detect common architectural patterns."""
        patterns = []
        content_all = ""

        for py_file in list(self.codebase_path.rglob("*.py"))[:50]:
            try:
                with open(py_file, encoding="utf-8", errors="replace") as f:
                    content_all += f.read() + "\n"
            except (PermissionError, OSError):
                pass

        pattern_checks = {
            "repository_pattern": ["repository", "Repository"],
            "factory_pattern": ["factory", "Factory", "create_"],
            "dependency_injection": ["inject", "Inject", "provider", "Provider"],
            "observer_pattern": ["observer", "Observer", "subscribe", "notify"],
            "strategy_pattern": ["strategy", "Strategy"],
            "decorator_pattern": ["decorator", "Decorator", "wraps"],
            "singleton_pattern": ["_instance", "singleton", "Singleton"],
            "middleware_pattern": ["middleware", "Middleware"],
            "pipeline_pattern": ["pipeline", "Pipeline"],
            "builder_pattern": ["builder", "Builder"],
        }

        for pattern_name, keywords in pattern_checks.items():
            if any(kw in content_all for kw in keywords):
                patterns.append(pattern_name)

        return patterns

    def _count_classes_in_files(self, files: list) -> int:
        count = 0
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line.strip().startswith("class "):
                            count += 1
            except (PermissionError, OSError):
                pass
        return count

    def _count_functions_in_files(self, files: list) -> int:
        count = 0
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        stripped = line.strip()
                        if stripped.startswith("def ") and not stripped.startswith("def _"):
                            count += 1
            except (PermissionError, OSError):
                pass
        return count

    def _count_files(self) -> int:
        count = 0
        for ext in ["*.py", "*.js", "*.ts", "*.tsx", "*.rs", "*.go", "*.java"]:
            count += len(list(self.codebase_path.rglob(ext)))
        return count

    def _count_lines(self) -> int:
        count = 0
        for ext in ["*.py", "*.js", "*.ts", "*.tsx", "*.rs", "*.go", "*.java"]:
            for f in self.codebase_path.rglob(ext):
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        count += sum(1 for _ in fh)
                except (PermissionError, OSError):
                    pass
        return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze codebase for AI-Scientist")
    parser.add_argument("path", help="Path to codebase")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    analyzer = CodebaseAnalyzer(args.path)
    result = analyzer.analyze()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Analysis written to {args.output}")
    else:
        print(json.dumps(result, indent=2))
