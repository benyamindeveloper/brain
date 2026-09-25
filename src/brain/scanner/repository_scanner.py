"""Repository scanner for discovering project structure and files."""

import os
from pathlib import Path
from typing import Optional
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from brain.models.core import FileEntity, Language, ArchitectureLayer


LANGUAGE_EXTENSIONS = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".java": Language.JAVA,
    ".cs": Language.CSHARP,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".h": Language.CPP,
    ".php": Language.PHP,
    ".rb": Language.RUBY,
    ".swift": Language.SWIFT,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
}

DEFAULT_IGNORE_PATTERNS = [
    ".git",
    "__pycache__",
    "*.pyc",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "env",
    ".env",
    "*.egg-info",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
    "bin",
    "obj",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".idea",
    ".vscode",
    "*.log",
    "*.tmp",
    "*.temp",
    "coverage",
    ".coverage",
    "htmlcov",
]


class RepositoryScanner:
    """Scans a repository and discovers source files with metadata."""

    def __init__(self, root_path: Path, ignore_patterns: Optional[list[str]] = None):
        self.root_path = root_path.resolve()
        self.ignore_patterns = ignore_patterns or DEFAULT_IGNORE_PATTERNS
        self._spec = PathSpec.from_lines(GitWildMatchPattern, self.ignore_patterns)

    def _is_ignored(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        try:
            rel_path = path.relative_to(self.root_path)
            return self._spec.match_file(str(rel_path))
        except ValueError:
            return True

    def _detect_language(self, path: Path) -> Language:
        """Detect programming language from file extension."""
        return LANGUAGE_EXTENSIONS.get(path.suffix.lower(), Language.UNKNOWN)

    def _detect_architecture_layer(self, rel_path: str) -> ArchitectureLayer:
        """Detect architecture layer from file path (heuristic)."""
        path_lower = rel_path.lower()

        layer_keywords = {
            ArchitectureLayer.PRESENTATION: [
                "presentation", "ui", "view", "component", "page", "screen",
                "controller", "api", "endpoint", "route", "handler"
            ],
            ArchitectureLayer.APPLICATION: [
                "application", "service", "usecase", "command", "query",
                "handler", "dto", "mapper", "facade"
            ],
            ArchitectureLayer.DOMAIN: [
                "domain", "model", "entity", "aggregate", "valueobject",
                "repository", "specification", "event", "policy"
            ],
            ArchitectureLayer.INFRASTRUCTURE: [
                "infrastructure", "data", "persistence", "repository",
                "database", "orm", "migration", "external", "adapter",
                "client", "gateway", "queue", "cache", "config"
            ],
            ArchitectureLayer.SHARED: [
                "shared", "common", "util", "helper", "extension",
                "base", "core", "kernel", "lib"
            ],
        }

        for layer, keywords in layer_keywords.items():
            if any(keyword in path_lower for keyword in keywords):
                return layer

        return ArchitectureLayer.UNKNOWN

    def scan(self) -> list[FileEntity]:
        """Scan the repository and return list of source files."""
        files = []

        for root, dirs, filenames in os.walk(self.root_path):
            root_path = Path(root)

            # Filter ignored directories in-place
            dirs[:] = [d for d in dirs if not self._is_ignored(root_path / d)]

            for filename in filenames:
                file_path = root_path / filename

                if self._is_ignored(file_path):
                    continue

                language = self._detect_language(file_path)
                if language == Language.UNKNOWN:
                    continue

                try:
                    stat = file_path.stat()
                    size_bytes = stat.st_size
                    last_modified = stat.st_mtime
                except OSError:
                    continue

                try:
                    rel_path = file_path.relative_to(self.root_path)
                except ValueError:
                    continue

                architecture_layer = self._detect_architecture_layer(str(rel_path))

                file_entity = FileEntity(
                    path=file_path,
                    relative_path=str(rel_path),
                    language=language,
                    size_bytes=size_bytes,
                    last_modified=last_modified,
                    architecture_layer=architecture_layer,
                )

                files.append(file_entity)

        return files

    def get_project_structure(self) -> dict:
        """Get a tree representation of the project structure."""
        structure = {"name": self.root_path.name, "type": "directory", "children": []}

        def build_tree(path: Path, node: dict):
            try:
                items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            except PermissionError:
                return

            for item in items:
                if self._is_ignored(item):
                    continue

                if item.is_dir():
                    child = {"name": item.name, "type": "directory", "children": []}
                    node["children"].append(child)
                    build_tree(item, child)
                else:
                    language = self._detect_language(item)
                    if language != Language.UNKNOWN:
                        node["children"].append({
                            "name": item.name,
                            "type": "file",
                            "language": language.value,
                        })

        build_tree(self.root_path, structure)
        return structure