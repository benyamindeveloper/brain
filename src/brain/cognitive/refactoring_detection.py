"""Refactoring Detection (14.2) - Evolution engine depth."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from collections import defaultdict
import re
from datetime import datetime
from pathlib import Path

from brain.models.core import EvolutionEventEntity, FileEntity, ClassEntity, FunctionEntity
from brain.cognitive.core import SemanticTriple, TripleType, KnowledgeGraph


class RefactoringType(str, Enum):
    """Types of refactoring detected."""
    RENAME_CLASS = "rename_class"
    RENAME_METHOD = "rename_method"
    RENAME_FILE = "rename_file"
    EXTRACT_CLASS = "extract_class"
    EXTRACT_METHOD = "extract_method"
    EXTRACT_INTERFACE = "extract_interface"
    INLINE_CLASS = "inline_class"
    INLINE_METHOD = "inline_method"
    MOVE_METHOD = "move_method"
    MOVE_FIELD = "move_field"
    PUSH_UP = "push_up"
    PULL_DOWN = "pull_down"
    REPLACE_INHERITANCE = "replace_inheritance"
    REPLACE_DELEGATION = "replace_delegation"
    INTRODUCE_PARAMETER = "introduce_parameter"
    REMOVE_PARAMETER = "remove_parameter"
    REORDER_PARAMETERS = "reorder_parameters"
    REPLACE_CONDITIONAL = "replace_conditional"
    EXTRACT_SUPERCLASS = "extract_superclass"
    EXTRACT_SUBCLASS = "extract_subclass"
    FORM_TEMPLATE_METHOD = "form_template_method"
    REPLACE_CONSTRUCTOR = "replace_constructor"
    COLLAPSE_HIERARCHY = "collapse_hierarchy"
    GENERALIZE = "generalize"
    UNKNOWN = "unknown"


@dataclass
class RefactoringInstance:
    """A detected refactoring instance."""
    refactoring_type: RefactoringType
    confidence: float
    timestamp: float
    commit_hash: str
    author: str
    affected_entities: List[str] = field(default_factory=list)
    description: str = ""
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefactoringPattern:
    """A pattern of related refactorings."""
    pattern_name: str
    instances: List[RefactoringInstance]
    frequency: int
    time_span: Tuple[float, float]
    affected_modules: List[str] = field(default_factory=list)


class RefactoringDetector:
    """Detects refactoring patterns from Git history and AST changes (14.2)."""
    
    def __init__(self, project_graph=None):
        self.project_graph = project_graph
        self.detected_refactorings: List[RefactoringInstance] = []
        self.refactoring_patterns: List[RefactoringPattern] = []
    
    def detect_from_git_history(self, project_root: Path, max_commits: int = 500) -> List[RefactoringInstance]:
        """Detect refactorings from Git commit history."""
        refactorings = []
        
        try:
            import subprocess
            # Get commit history with stats
            result = subprocess.run([
                "git", "log", 
                f"--max-count={max_commits}",
                "--pretty=format:%H|%an|%at|%s",
                "--numstat",
                "--diff-filter=M"
            ], cwd=project_root, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                return []
            
            # Parse git log output
            refactorings = self._parse_git_log(result.stdout, project_root)
            
        except Exception as e:
            pass
        
        self.detected_refactorings = refactorings
        return refactorings
    
    def _parse_git_log(self, log_output: str, project_root: Path) -> List[RefactoringInstance]:
        """Parse git log output to detect refactorings."""
        refactorings = []
        lines = log_output.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Parse commit header: hash|author|timestamp|message
            if '|' in line and line.count('|') >= 3:
                parts = line.split('|', 3)
                if len(parts) >= 4:
                    commit_hash, author, timestamp_str, message = parts[:4]
                    timestamp = float(timestamp_str) if timestamp_str.isdigit() else 0
                    
                    # Collect numstat lines
                    numstat_lines = []
                    i += 1
                    while i < len(lines) and lines[i].strip() and '\t' in lines[i]:
                        numstat_lines.append(lines[i].strip())
                        i += 1
                    
                    # Analyze this commit for refactorings
                    commit_refactorings = self._analyze_commit(
                        commit_hash, author, timestamp, message, numstat_lines, project_root
                    )
                    refactorings.extend(commit_refactorings)
                    continue
            i += 1
        
        return refactorings
    
    def _analyze_commit(self, commit_hash: str, author: str, timestamp: float, 
                       message: str, numstat_lines: List[str], project_root: Path) -> List[RefactoringInstance]:
        """Analyze a single commit for refactoring patterns."""
        refactorings = []
        
        # Check commit message for refactoring keywords
        msg_lower = message.lower()
        explicit_type = self._classify_refactoring_from_message(message)
        
        # Parse numstat for file changes
        file_changes = []
        for line in numstat_lines:
            parts = line.split('\t')
            if len(parts) >= 3:
                added, deleted, filepath = parts[0], parts[1], parts[2]
                file_changes.append({
                    "file": filepath,
                    "added": int(added) if added != '-' else 0,
                    "deleted": int(deleted) if deleted != '-' else 0,
                })
        
        # Detect specific refactoring types
        if explicit_type != RefactoringType.UNKNOWN:
            refactorings.append(RefactoringInstance(
                refactoring_type=explicit_type,
                confidence=0.8,
                timestamp=timestamp,
                commit_hash=commit_hash[:8],
                author=author,
                description=message[:200],
                affected_entities=[fc["file"] for fc in file_changes],
                metadata={"message": message, "explicit": True},
            ))
        
        # Detect rename patterns from file changes
        rename_refactorings = self._detect_renames(file_changes, commit_hash, author, timestamp, message)
        refactorings.extend(rename_refactorings)
        
        # Detect extract method/class from line changes
        extract_refactorings = self._detect_extracts(file_changes, commit_hash, author, timestamp, message)
        refactorings.extend(extract_refactorings)
        
        # Detect move operations
        move_refactorings = self._detect_moves(file_changes, commit_hash, author, timestamp, message)
        refactorings.extend(move_refactorings)
        
        return refactorings
    
    def _classify_refactoring_from_message(self, message: str) -> RefactoringType:
        """Classify refactoring type from commit message."""
        msg = message.lower()
        
        refactoring_keywords = {
            RefactoringType.RENAME_CLASS: ["rename class", "rename type"],
            RefactoringType.RENAME_METHOD: ["rename method", "rename function"],
            RefactoringType.RENAME_FILE: ["rename file", "move file"],
            RefactoringType.EXTRACT_CLASS: ["extract class", "extract type"],
            RefactoringType.EXTRACT_METHOD: ["extract method", "extract function"],
            RefactoringType.EXTRACT_INTERFACE: ["extract interface"],
            RefactoringType.INLINE_CLASS: ["inline class"],
            RefactoringType.INLINE_METHOD: ["inline method", "inline function"],
            RefactoringType.MOVE_METHOD: ["move method", "move function"],
            RefactoringType.MOVE_FIELD: ["move field", "move property"],
            RefactoringType.PUSH_UP: ["push up", "pull up"],
            RefactoringType.PULL_DOWN: ["pull down", "push down"],
            RefactoringType.REPLACE_INHERITANCE: ["replace inheritance", "composition over inheritance"],
            RefactoringType.EXTRACT_SUPERCLASS: ["extract superclass"],
            RefactoringType.EXTRACT_SUBCLASS: ["extract subclass"],
            RefactoringType.FORM_TEMPLATE_METHOD: ["template method"],
            RefactoringType.REPLACE_CONSTRUCTOR: ["factory method", "replace constructor"],
        }
        
        for ref_type, keywords in refactoring_keywords.items():
            if any(kw in msg for kw in keywords):
                return ref_type
        
        return RefactoringType.UNKNOWN
    
    def _detect_renames(self, file_changes, commit_hash, author, timestamp, message) -> List[RefactoringInstance]:
        """Detect rename operations from file changes."""
        refactorings = []
        
        # Look for deleted + added file pairs (potential renames)
        deleted_files = [fc for fc in file_changes if fc["deleted"] > 0 and fc["added"] == 0]
        added_files = [fc for fc in file_changes if fc["added"] > 0 and fc["deleted"] == 0]
        
        for deleted in deleted_files:
            for added in added_files:
                similarity = self._calculate_filename_similarity(deleted["file"], added["file"])
                if similarity > 0.7:
                    refactorings.append(RefactoringInstance(
                        refactoring_type=RefactoringType.RENAME_FILE,
                        confidence=similarity,
                        timestamp=0,  # Will be set by caller
                        commit_hash="",
                        author="",
                        affected_entities=[deleted["file"], added["file"]],
                        description=f"Rename {deleted['file']} -> {added['file']}",
                        before_state={"file": deleted["file"]},
                        after_state={"file": added["file"]},
                    ))
        
        return refactorings
    
    def _calculate_filename_similarity(self, file1: str, file2: str) -> float:
        """Calculate similarity between two file paths."""
        import difflib
        # Compare base names
        name1 = Path(file1).stem
        name2 = Path(file2).stem
        return difflib.SequenceMatcher(None, name1, name2).ratio()
    
    def _detect_extracts(self, file_changes, commit_hash, author, timestamp, message) -> List[RefactoringInstance]:
        """Detect extract method/class refactorings."""
        refactorings = []
        
        # Look for files with significant additions and deletions (possible extract)
        for fc in file_changes:
            if fc["added"] > 50 and fc["deleted"] > 20:
                # High churn - possible extract
                ratio = fc["added"] / max(fc["deleted"], 1)
                if 1.5 < ratio < 5:
                    refactorings.append(RefactoringInstance(
                        refactoring_type=RefactoringType.EXTRACT_METHOD,
                        confidence=0.6,
                        timestamp=0,
                        commit_hash="",
                        author="",
                        affected_entities=[fc["file"]],
                        description=f"Possible extract method in {fc['file']}",
                        metadata={"added_lines": fc["added"], "deleted_lines": fc["deleted"]},
                    ))
        
        return refactorings
    
    def _detect_moves(self, file_changes, commit_hash, author, timestamp, message) -> List[RefactoringInstance]:
        """Detect move method/field operations."""
        refactorings = []
        # This would require more sophisticated AST diffing
        # For now, return empty
        return refactorings
    
    def detect_from_ast_changes(self, old_ast: str, new_ast: str, file_path: str) -> List[RefactoringInstance]:
        """Detect refactorings from AST comparison (for real-time detection)."""
        refactorings = []
        
        # This would require actual AST parsing
        # For now, placeholder for future implementation
        return refactorings
    
    def find_refactoring_patterns(self, min_frequency: int = 3) -> List[RefactoringPattern]:
        """Find recurring refactoring patterns."""
        patterns = []
        
        # Group by type
        by_type = defaultdict(list)
        for r in self.detected_refactorings:
            by_type[r.refactoring_type].append(r)
        
        for ref_type, instances in by_type.items():
            if len(instances) >= min_frequency:
                # Check if they affect similar modules
                modules = set()
                for inst in instances:
                    for entity in inst.affected_entities:
                        # Extract module from path
                        parts = entity.split('/')
                        if len(parts) > 1:
                            modules.add(parts[0])
                
                if len(modules) >= 2:  # Affects multiple modules
                    patterns.append(RefactoringPattern(
                        pattern_name=f"Repeated {ref_type.value}",
                        instances=instances,
                        frequency=len(instances),
                        time_span=(instances[0].timestamp, instances[-1].timestamp),
                        affected_modules=list(modules),
                    ))
        
        self.refactoring_patterns = patterns
        return patterns
    
    def get_refactoring_summary(self) -> Dict[str, Any]:
        """Get summary of detected refactorings."""
        by_type = defaultdict(int)
        by_author = defaultdict(int)
        by_month = defaultdict(int)
        
        for r in self.detected_refactorings:
            by_type[r.refactoring_type.value] += 1
            by_author[r.author] += 1
            # Group by month
            dt = datetime.fromtimestamp(r.timestamp)
            month_key = dt.strftime("%Y-%m")
            by_month[month_key] += 1
        
        return {
            "total_refactorings": len(self.detected_refactorings),
            "by_type": dict(by_type),
            "by_author": dict(by_author),
            "by_month": dict(by_month),
            "patterns_found": len(self.refactoring_patterns),
        }


class EvolutionAnalyzer:
    """Analyzes evolution patterns and trends (14.1, 14.2)."""
    
    def __init__(self, project_graph=None):
        self.project_graph = project_graph
    
    def analyze_architecture_drift(self) -> Dict[str, Any]:
        """Analyze architecture drift over time."""
        if not self.project_graph:
            return {}
        
        drift = {
            "layer_violations_over_time": [],
            "dependency_changes": [],
            "pattern_degradation": [],
        }
        
        # Analyze evolution events for layer violations
        for event in self.project_graph.evolution_events:
            if event.event_type == "refactor":
                # Check if refactor introduced violations
                pass
        
        return drift
    
    def analyze_module_stability(self) -> Dict[str, float]:
        """Calculate stability metrics for modules."""
        if not self.project_graph:
            return {}
        
        stability = {}
        
        for file_path, file_entity in self.project_graph.files.items():
            if file_entity.git_history:
                changes = file_entity.git_history.commits_count
                frequency = file_entity.git_history.change_frequency
                # Stability = inverse of change frequency
                stability[file_path] = 1.0 / (1.0 + frequency)
            else:
                stability[file_path] = 1.0
        
        return stability
    
    def analyze_coupling_trends(self) -> Dict[str, List[float]]:
        """Analyze coupling trends over time."""
        # This would require historical dependency data
        return {}
    
    def identify_technical_debt_hotspots(self) -> List[Dict[str, Any]]:
        """Identify areas accumulating technical debt."""
        hotspots = []
        
        if not self.project_graph:
            return hotspots
        
        for file_path, file_entity in self.project_graph.files.items():
            debt_score = 0.0
            reasons = []
            
            # High change frequency
            if file_entity.git_history and file_entity.git_history.change_frequency > 5:
                debt_score += 2.0
                reasons.append(f"High change frequency: {file_entity.git_history.change_frequency:.1f}/month")
            
            # Many dependencies
            deps = len([d for d in self.project_graph.dependencies if d.source == file_path])
            if deps > 10:
                debt_score += 1.5
                reasons.append(f"High dependencies: {deps}")
            
            # Business rules violations
            rule_count = sum(1 for r in self.project_graph.business_rules if file_path in r.source_files)
            if rule_count > 3:
                debt_score += 1.0
                reasons.append(f"Many business rules: {rule_count}")
            
            # Architecture violations
            violations = sum(1 for v in self.project_graph.metadata.get("architecture_violations", []) if v.get("source_file") == file_path)
            if violations > 0:
                debt_score += violations * 0.5
                reasons.append(f"Architecture violations: {violations}")
            
            if debt_score > 2.0:
                hotspots.append({
                    "file": file_path,
                    "debt_score": debt_score,
                    "reasons": reasons,
                    "change_frequency": file_entity.git_history.change_frequency if file_entity.git_history else 0,
                })
        
        return sorted(hotspots, key=lambda x: x["debt_score"], reverse=True)


def create_refactoring_detector(project_graph=None) -> RefactoringDetector:
    """Factory function to create refactoring detector."""
    return RefactoringDetector(project_graph)


def create_evolution_analyzer(project_graph=None) -> EvolutionAnalyzer:
    """Factory function to create evolution analyzer."""
    return EvolutionAnalyzer(project_graph)