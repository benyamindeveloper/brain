"""Git history analyzer for evolution tracking."""

from collections import defaultdict
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from git import Repo, InvalidGitRepositoryError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

from brain.models.core import (
    FileEntity, EvolutionEventEntity, GitHistory, ArchitectureLayer
)


class GitAnalyzer:
    """Analyzes Git history to extract evolution events and file history."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.repo: Optional[Repo] = None
        self._init_repo()

    def _init_repo(self):
        """Initialize Git repo if available."""
        if not GIT_AVAILABLE:
            return
        try:
            self.repo = Repo(self.repo_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, ValueError):
            self.repo = None

    def is_available(self) -> bool:
        """Check if Git analysis is available."""
        return self.repo is not None

    def analyze_file_history(self, file_entity: FileEntity) -> GitHistory:
        """Analyze Git history for a specific file."""
        if not self.is_available():
            return GitHistory()

        try:
            rel_path = file_entity.relative_path
            commits = list(self.repo.iter_commits(paths=rel_path, max_count=100))

            if not commits:
                return GitHistory()

            authors = set()
            timestamps = []
            major_refactors = []

            for commit in commits:
                authors.add(commit.author.name)
                timestamps.append(commit.committed_date)

                # Detect major refactors (large diffs, many files)
                if commit.stats.total["lines"] > 200:
                    major_refactors.append(commit.hexsha[:8])

            # Calculate change frequency (changes per month)
            if len(timestamps) >= 2:
                time_span = max(timestamps) - min(timestamps)
                months = max(time_span / (30 * 24 * 3600), 1)
                change_freq = len(commits) / months
            else:
                change_freq = 0.0

            return GitHistory(
                commits_count=len(commits),
                authors=list(authors),
                last_change=max(timestamps) if timestamps else None,
                change_frequency=change_freq,
                major_refactors=major_refactors[:10],
            )

        except Exception:
            return GitHistory()

    def analyze_recent_commits(self, max_commits: int = 50) -> list[EvolutionEventEntity]:
        """Analyze recent commits for evolution events."""
        if not self.is_available():
            return []

        events = []
        try:
            commits = list(self.repo.iter_commits(max_count=max_commits))

            for commit in commits:
                event_type = self._classify_commit(commit)
                files_changed = list(commit.stats.files.keys())
                impact_score = self._calculate_impact(commit, files_changed)

                event = EvolutionEventEntity(
                    commit_hash=commit.hexsha[:8],
                    timestamp=commit.committed_date,
                    author=commit.author.name,
                    message=commit.message.strip(),
                    files_changed=files_changed,
                    event_type=event_type,
                    impact_score=impact_score,
                    related_issues=self._extract_issues(commit.message),
                )
                events.append(event)

        except Exception:
            pass

        return events

    def _classify_commit(self, commit) -> str:
        """Classify commit type based on message and stats."""
        msg = commit.message.lower()

        if any(kw in msg for kw in ["refactor", "restructure", "reorganize"]):
            return "refactor"
        elif any(kw in msg for kw in ["fix", "bug", "patch", "hotfix"]):
            return "fix"
        elif any(kw in msg for kw in ["feat", "feature", "add", "implement"]):
            return "feature"
        elif any(kw in msg for kw in ["doc", "readme", "comment"]):
            return "docs"
        elif any(kw in msg for kw in ["test", "spec"]):
            return "test"
        elif any(kw in msg for kw in ["chore", "build", "ci", "config", "dep"]):
            return "chore"
        else:
            return "other"

    def _calculate_impact(self, commit, files_changed: list[str]) -> float:
        """Calculate impact score based on diff stats."""
        try:
            total_lines = commit.stats.total["lines"]
            num_files = len(files_changed)

            # Base score from lines changed
            score = min(total_lines / 100.0, 5.0)

            # Boost for multi-file changes
            if num_files > 5:
                score += 1.0
            elif num_files > 1:
                score += 0.5

            # Boost for core files
            core_patterns = ["core.py", "__init__.py", "config", "model", "entity"]
            for f in files_changed:
                if any(p in f.lower() for p in core_patterns):
                    score += 0.5
                    break

            return min(score, 10.0)
        except Exception:
            return 1.0

    def _extract_issues(self, message: str) -> list[str]:
        """Extract issue references from commit message."""
        import re
        # Match patterns like #123, GH-123, JIRA-123, etc.
        patterns = [
            r"#(\d+)",
            r"GH-(\d+)",
            r"JIRA-(\d+)",
            r"ISSUE-(\d+)",
        ]
        issues = []
        for pattern in patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            issues.extend(matches)
        return issues

    def get_file_ownership(self, file_entities: dict[str, FileEntity]) -> dict[str, list[str]]:
        """Get code ownership patterns (top contributors per file)."""
        if not self.is_available():
            return {}

        ownership = defaultdict(lambda: defaultdict(int))

        try:
            for rel_path in file_entities.keys():
                commits = list(self.repo.iter_commits(paths=rel_path, max_count=50))
                for commit in commits:
                    ownership[rel_path][commit.author.name] += 1
        except Exception:
            pass

        # Convert to top contributors per file
        result = {}
        for file_path, authors in ownership.items():
            top_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:3]
            result[file_path] = [author for author, _ in top_authors]

        return result

    def get_hotspots(self, file_entities: dict[str, FileEntity], threshold: float = 5.0) -> list[dict]:
        """Identify code hotspots (frequently changed, complex files)."""
        if not self.is_available():
            return []

        hotspots = []

        try:
            for rel_path, file_entity in file_entities.items():
                history = self.analyze_file_history(file_entity)
                if history.change_frequency >= threshold:
                    hotspots.append({
                        "file": rel_path,
                        "change_frequency": history.change_frequency,
                        "commits_count": history.commits_count,
                        "authors": history.authors,
                        "major_refactors": history.major_refactors,
                    })
        except Exception:
            pass

        return sorted(hotspots, key=lambda x: x["change_frequency"], reverse=True)