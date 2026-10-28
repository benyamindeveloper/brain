"""Context generator for creating .brain-context.md and .brain-context.json files."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional
from datetime import datetime

from brain.models.core import (
    FileEntity, ClassEntity, FunctionEntity, DependencyEntity,
    ArchitectureLayer, ArchitectureLayerEntity, ArchitectureAnalysis,
    BusinessRuleEntity, EvolutionEventEntity, ProjectGraph, Language, GitHistory
)
from brain.analyzer.dependency_analyzer import DependencyAnalyzer, DependencyGraph
from brain.analyzer.architecture_analyzer import ArchitectureAnalyzer
from brain.analyzer.git_analyzer import GitAnalyzer
from brain.analyzer.business_rule_extractor import BusinessRuleExtractor
from brain.storage.sqlite_storage import SQLiteStorage


class ContextGenerator:
    """Generates compressed context files for LLM consumption."""

    def __init__(self, project_root: Path, project_name: Optional[str] = None, use_persistent_storage: bool = True):
        self.project_root = project_root
        self.project_name = project_name or project_root.name
        self.project_graph = ProjectGraph()
        self.dependency_graph: Optional[DependencyGraph] = None
        self.architecture_analysis: Optional[ArchitectureAnalysis] = None
        self.dependency_analyzer = DependencyAnalyzer()
        self.architecture_analyzer = ArchitectureAnalyzer()
        self.git_analyzer = GitAnalyzer(project_root)
        self.business_rule_extractor = BusinessRuleExtractor()

        # Persistent storage
        self.use_persistent_storage = use_persistent_storage
        self.storage: Optional[SQLiteStorage] = None
        if use_persistent_storage:
            db_path = project_root / ".brain" / "brain.db"
            self.storage = SQLiteStorage(db_path)

    def add_file_entity(self, file_entity: FileEntity):
        """Add a file entity to the project graph."""
        self.project_graph.files[file_entity.relative_path] = file_entity
        self.dependency_analyzer.add_file(file_entity)
        self.architecture_analyzer.add_file(file_entity)

    def add_class_entity(self, class_entity: ClassEntity):
        """Add a class entity."""
        self.project_graph.classes[class_entity.qualified_name] = class_entity
        self.architecture_analyzer.add_class(class_entity)

    def add_function_entity(self, function_entity: FunctionEntity):
        """Add a function entity."""
        self.project_graph.functions[function_entity.qualified_name] = function_entity
        self.architecture_analyzer.add_function(function_entity)

    def load_from_storage(self) -> bool:
        """Load project graph from persistent storage. Returns True if loaded."""
        if not self.storage:
            return False
        try:
            self.project_graph = self.storage.load_project_graph()
            if len(self.project_graph.files) == 0:
                return False
            
            # Re-populate analyzers with loaded data
            self._repopulate_analyzers()
            
            # Run analysis on loaded data
            self.finalize()
            return True
        except Exception:
            return False

    def _repopulate_analyzers(self):
        """Re-populate analyzers with data from loaded project graph."""
        for file_entity in self.project_graph.files.values():
            self.dependency_analyzer.add_file(file_entity)
            self.architecture_analyzer.add_file(file_entity)
        
        for class_entity in self.project_graph.classes.values():
            self.architecture_analyzer.add_class(class_entity)
        
        for func_entity in self.project_graph.functions.values():
            self.architecture_analyzer.add_function(func_entity)

    def save_to_storage(self):
        """Save project graph to persistent storage."""
        if self.storage:
            self.storage.save_project_graph(self.project_graph)
            # Save cognitive model
            if "cognitive_model" in self.project_graph.metadata:
                self.storage.save_cognitive_model(self.project_graph, self.project_graph.metadata["cognitive_model"])

    def finalize(self):
        """Finalize analysis and build graphs."""
        self.dependency_graph = self.dependency_analyzer.analyze()
        self.architecture_analysis = self.architecture_analyzer.analyze()

        # Git history analysis
        if self.git_analyzer.is_available():
            self._analyze_git_history()

        # Business rule extraction
        self._extract_business_rules()

        # Build cognitive model
        self._build_cognitive_model()

        # Add to project graph
        self.project_graph.dependencies = self.dependency_graph.internal_dependencies
        self.project_graph.architecture_layers = self.architecture_analysis.layers
        self.project_graph.metadata = {
            "project_name": self.project_name,
            "project_root": str(self.project_root),
            "generated_at": datetime.now().isoformat(),
            "total_files": len(self.project_graph.files),
            "total_classes": len(self.project_graph.classes),
            "total_functions": len(self.project_graph.functions),
            "total_dependencies": len(self.project_graph.dependencies),
            "languages": self._get_languages(),
            "architecture_patterns": self.architecture_analysis.detected_patterns,
        }

    def _build_cognitive_model(self):
        """Build the cognitive model (KnowledgeGraph, embeddings, memory layers)."""
        from brain.cognitive import CognitiveProjectModel
        self.cognitive_model = CognitiveProjectModel(self.project_graph)
        self.cognitive_model.build()
        # Store in project graph metadata for persistence
        self.project_graph.metadata["cognitive_model"] = self.cognitive_model

    def _get_languages(self) -> list[str]:
        """Get list of languages in the project."""
        languages = set()
        for f in self.project_graph.files.values():
            languages.add(f.language.value)
        return sorted(languages)

    def _analyze_git_history(self):
        """Analyze Git history for evolution events and file history."""
        # Analyze recent commits for evolution events
        self.project_graph.evolution_events = self.git_analyzer.analyze_recent_commits(max_commits=100)

        # Analyze file history for each file
        for file_entity in self.project_graph.files.values():
            history = self.git_analyzer.analyze_file_history(file_entity)
            file_entity.git_history = history

        # Identify hotspots
        hotspots = self.git_analyzer.get_hotspots(self.project_graph.files)
        if hotspots:
            self.project_graph.metadata["git_hotspots"] = hotspots[:10]

    def _extract_business_rules(self):
        """Extract business rules from source code."""
        for file_entity in self.project_graph.files.values():
            if file_entity.language != Language.PYTHON:
                continue

            # Get classes and functions for this file
            file_classes = {
                k: v for k, v in self.project_graph.classes.items()
                if v.file_path == file_entity.relative_path
            }
            file_functions = {
                k: v for k, v in self.project_graph.functions.items()
                if v.file_path == file_entity.relative_path
            }

            rules = self.business_rule_extractor.extract_from_file(
                file_entity, file_classes, file_functions
            )
            self.project_graph.business_rules.extend(rules)

        # Sort by priority
        self.project_graph.business_rules.sort(key=lambda r: r.priority)

    def generate_markdown(self, output_path: Path, max_tokens: int = 8000) -> str:
        """Generate .brain-context.md file."""
        self.finalize()

        lines = []
        lines.append(f"# {self.project_name} - Project Brain Context")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Project Root:** {self.project_root}")
        lines.append(f"**Total Files:** {len(self.project_graph.files)}")
        lines.append(f"**Total Classes:** {len(self.project_graph.classes)}")
        lines.append(f"**Total Functions:** {len(self.project_graph.functions)}")
        lines.append(f"**Languages:** {', '.join(self._get_languages())}")
        lines.append("")

        # Architecture Overview
        lines.append("## Architecture Overview")
        lines.append("")
        if self.architecture_analysis.detected_patterns:
            lines.append(f"**Detected Patterns:** {', '.join(self.architecture_analysis.detected_patterns)}")
        else:
            lines.append("**Detected Patterns:** None clearly identified")
        lines.append("")

        # Layers
        lines.append("### Architecture Layers")
        lines.append("")
        for layer in ArchitectureLayer:
            if layer == ArchitectureLayer.UNKNOWN:
                continue
            layer_entity = self.architecture_analysis.layers.get(layer)
            if layer_entity and (layer_entity.files or layer_entity.classes):
                lines.append(f"#### {layer.value.title()}")
                lines.append(f"{layer_entity.description}")
                lines.append("")
                if layer_entity.files:
                    lines.append(f"**Files ({len(layer_entity.files)}):**")
                    for f in sorted(layer_entity.files)[:20]:
                        lines.append(f"- `{f}`")
                    if len(layer_entity.files) > 20:
                        lines.append(f"- ... and {len(layer_entity.files) - 20} more")
                    lines.append("")
                if layer_entity.classes:
                    lines.append(f"**Key Classes ({len(layer_entity.classes)}):**")
                    for c in sorted(layer_entity.classes)[:15]:
                        lines.append(f"- `{c}`")
                    if len(layer_entity.classes) > 15:
                        lines.append(f"- ... and {len(layer_entity.classes) - 15} more")
                    lines.append("")

        # Key Components
        lines.append("## Key Components")
        lines.append("")

        # Top classes by complexity/importance
        lines.append("### Classes")
        lines.append("")
        sorted_classes = sorted(
            self.project_graph.classes.values(),
            key=lambda c: len(c.methods) + len(c.properties),
            reverse=True
        )
        for cls in sorted_classes[:30]:
            lines.append(f"#### `{cls.qualified_name}`")
            lines.append(f"- **File:** `{cls.file_path}` (lines {cls.line_start}-{cls.line_end})")
            if cls.base_classes:
                lines.append(f"- **Inherits:** {', '.join(cls.base_classes)}")
            if cls.implemented_interfaces:
                lines.append(f"- **Implements:** {', '.join(cls.implemented_interfaces)}")
            if cls.methods:
                lines.append(f"- **Methods ({len(cls.methods)}):** {', '.join(cls.methods[:10])}")
                if len(cls.methods) > 10:
                    lines.append(f"  - ... and {len(cls.methods) - 10} more")
            if cls.properties:
                lines.append(f"- **Properties ({len(cls.properties)}):** {', '.join(cls.properties[:10])}")
            if cls.docstring:
                lines.append(f"- **Description:** {cls.docstring[:200]}")
            lines.append("")

        # Top functions
        lines.append("### Functions")
        lines.append("")
        sorted_functions = sorted(
            self.project_graph.functions.values(),
            key=lambda f: f.complexity,
            reverse=True
        )
        for func in sorted_functions[:20]:
            if func.is_method:
                continue
            lines.append(f"- `{func.qualified_name}` ({func.file_path}:{func.line_start})")
            if func.parameters:
                lines.append(f"  - Params: {', '.join(func.parameters)}")
            if func.return_type:
                lines.append(f"  - Returns: {func.return_type}")
            if func.is_async:
                lines.append(f"  - **Async**")
            if func.docstring:
                lines.append(f"  - {func.docstring[:150]}")
        lines.append("")

        # Dependencies
        lines.append("## Dependency Analysis")
        lines.append("")

        # Internal dependencies summary
        internal_deps = [d for d in self.project_graph.dependencies if d.dependency_type == "import"]
        lines.append(f"**Internal Dependencies:** {len(internal_deps)}")
        lines.append("")

        # Circular dependencies
        if self.dependency_graph and self.dependency_graph.circular_dependencies:
            lines.append("### ⚠️ Circular Dependencies Detected")
            lines.append("")
            for cycle in self.dependency_graph.circular_dependencies[:5]:
                lines.append(f"- {' → '.join(cycle)} → {cycle[0]}")
            lines.append("")

        # External dependencies
        if self.dependency_graph and self.dependency_graph.external_dependencies:
            lines.append("### External Dependencies")
            lines.append("")
            for dep in sorted(self.dependency_graph.external_dependencies)[:30]:
                lines.append(f"- `{dep}`")
            if len(self.dependency_graph.external_dependencies) > 30:
                lines.append(f"- ... and {len(self.dependency_graph.external_dependencies) - 30} more")
            lines.append("")

        # Layer violations
        if self.architecture_analysis and self.architecture_analysis.layer_violations:
            lines.append("### ⚠️ Architecture Layer Violations")
            lines.append("")
            for v in self.architecture_analysis.layer_violations[:10]:
                lines.append(f"- `{v['source_file']}` ({v['source_layer']}) → `{v['target_file']}` ({v['target_layer']}) via `{v['import']}`")
            lines.append("")

        # Evolution & Git History
        if self.project_graph.evolution_events:
            lines.append("## Evolution History")
            lines.append("")

            # Recent events
            lines.append("### Recent Changes")
            lines.append("")
            for event in self.project_graph.evolution_events[:15]:
                dt = datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d %H:%M')
                lines.append(f"- **{event.commit_hash}** ({dt}) - {event.event_type.upper()}: {event.message[:100]}")
                if event.files_changed:
                    lines.append(f"  Files: {', '.join(event.files_changed[:5])}{'...' if len(event.files_changed) > 5 else ''}")
                if event.related_issues:
                    lines.append(f"  Issues: {', '.join(event.related_issues)}")
            lines.append("")

            # Hotspots
            if "git_hotspots" in self.project_graph.metadata:
                lines.append("### ⚠️ Code Hotspots (Frequently Changed)")
                lines.append("")
                for hs in self.project_graph.metadata["git_hotspots"][:5]:
                    lines.append(f"- `{hs['file']}`: {hs['change_frequency']:.1f} changes/month, {hs['commits_count']} commits, authors: {', '.join(hs['authors'][:3])}")
                lines.append("")

        # Business Rules
        if self.project_graph.business_rules:
            lines.append("## Business Rules")
            lines.append("")

            # Group by type
            by_type = defaultdict(list)
            for rule in self.project_graph.business_rules:
                by_type[rule.rule_type].append(rule)

            type_order = ["invariant", "validation", "constraint", "workflow"]
            for rule_type in type_order:
                if rule_type not in by_type:
                    continue
                rules = by_type[rule_type]
                lines.append(f"### {rule_type.title()} Rules ({len(rules)})")
                lines.append("")
                for rule in rules[:10]:
                    lines.append(f"- **{rule.id}**: {rule.name}")
                    lines.append(f"  {rule.description}")
                    if rule.source_files:
                        lines.append(f"  Source: {', '.join(rule.source_files)}")
                    lines.append("")
                if len(rules) > 10:
                    lines.append(f"  ... and {len(rules) - 10} more {rule_type} rules")
                    lines.append("")

            # Other types
            for rule_type, rules in by_type.items():
                if rule_type in type_order:
                    continue
                lines.append(f"### {rule_type.title()} Rules ({len(rules)})")
                lines.append("")
                for rule in rules[:10]:
                    lines.append(f"- **{rule.id}**: {rule.name}")
                    lines.append(f"  {rule.description}")
                    lines.append("")
                if len(rules) > 10:
                    lines.append(f"  ... and {len(rules) - 10} more {rule_type} rules")
                    lines.append("")

        # File Index
        lines.append("## File Index")
        lines.append("")
        for f in sorted(self.project_graph.files.values(), key=lambda x: x.relative_path):
            git_info = ""
            if f.git_history and f.git_history.commits_count > 0:
                git_info = f", {f.git_history.commits_count} commits, {f.git_history.change_frequency:.1f} changes/mo"
            lines.append(f"- `{f.relative_path}` ({f.language.value}, {f.lines_of_code} LOC, {f.architecture_layer.value}{git_info})")

        content = "\n".join(lines)

        # Apply token limit (rough estimation: 1 token ≈ 4 chars)
        if len(content) > max_tokens * 4:
            content = self._compress_content(content, max_tokens)

        output_path.write_text(content, encoding="utf-8")
        return content

    def _compress_content(self, content: str, max_tokens: int) -> str:
        """Compress content to fit token limit."""
        target_chars = max_tokens * 4
        if len(content) <= target_chars:
            return content

        # Keep header, architecture, and key components; truncate file index
        sections = content.split("\n## ")
        if len(sections) > 3:
            kept = "\n## ".join(sections[:3])
            kept += "\n## File Index (truncated)"
            kept += f"\n- ... {len(self.project_graph.files)} files total (see JSON for full list)"
            return kept[:target_chars]

        return content[:target_chars]

    def generate_json(self, output_path: Path) -> dict:
        """Generate .brain-context.json file."""
        self.finalize()

        data = {
            "metadata": self.project_graph.metadata,
            "files": {
                path: {
                    "path": str(f.path),
                    "relative_path": f.relative_path,
                    "language": f.language.value,
                    "size_bytes": f.size_bytes,
                    "lines_of_code": f.lines_of_code,
                    "imports": f.imports,
                    "exports": f.exports,
                    "classes": f.classes,
                    "functions": f.functions,
                    "architecture_layer": f.architecture_layer.value,
                    "last_modified": f.last_modified,
                }
                for path, f in self.project_graph.files.items()
            },
            "classes": {
                name: {
                    "name": c.name,
                    "qualified_name": c.qualified_name,
                    "file_path": c.file_path,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "methods": c.methods,
                    "properties": c.properties,
                    "base_classes": c.base_classes,
                    "implemented_interfaces": c.implemented_interfaces,
                    "decorators": c.decorators,
                    "is_abstract": c.is_abstract,
                    "is_interface": c.is_interface,
                    "docstring": c.docstring,
                }
                for name, c in self.project_graph.classes.items()
            },
            "functions": {
                name: {
                    "name": f.name,
                    "qualified_name": f.qualified_name,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "parameters": f.parameters,
                    "return_type": f.return_type,
                    "decorators": f.decorators,
                    "is_async": f.is_async,
                    "is_method": f.is_method,
                    "class_name": f.class_name,
                    "docstring": f.docstring,
                    "complexity": f.complexity,
                }
                for name, f in self.project_graph.functions.items()
            },
            "dependencies": [
                {
                    "source": d.source,
                    "target": d.target,
                    "dependency_type": d.dependency_type,
                    "strength": d.strength,
                    "metadata": d.metadata,
                }
                for d in self.project_graph.dependencies
            ],
            "architecture": {
                "patterns": self.architecture_analysis.detected_patterns if self.architecture_analysis else [],
                "layers": {
                    layer.value: {
                        "name": layer_entity.name.value,
                        "description": layer_entity.description,
                        "files": layer_entity.files,
                        "classes": layer_entity.classes,
                        "allowed_dependencies": [l.value for l in layer_entity.allowed_dependencies],
                        "forbidden_dependencies": [l.value for l in layer_entity.forbidden_dependencies],
                    }
                    for layer, layer_entity in self.architecture_analysis.layers.items()
                } if self.architecture_analysis else {},
                "violations": self.architecture_analysis.layer_violations if self.architecture_analysis else [],
                "metrics": self.architecture_analysis.metrics if self.architecture_analysis else {},
            },
            "dependency_graph": {
                "internal_dependencies": len([d for d in self.project_graph.dependencies if d.dependency_type == "import"]),
                "external_dependencies": self.dependency_graph.external_dependencies if self.dependency_graph else [],
                "circular_dependencies": self.dependency_graph.circular_dependencies if self.dependency_graph else [],
                "stats": self.dependency_analyzer.get_dependency_stats(self.dependency_graph),
            } if self.dependency_graph else {},
            "evolution": {
                "events": [
                    {
                        "commit_hash": e.commit_hash,
                        "timestamp": e.timestamp,
                        "date": datetime.fromtimestamp(e.timestamp).isoformat(),
                        "author": e.author,
                        "message": e.message,
                        "files_changed": e.files_changed,
                        "event_type": e.event_type,
                        "impact_score": e.impact_score,
                        "related_issues": e.related_issues,
                    }
                    for e in self.project_graph.evolution_events
                ],
                "hotspots": self.project_graph.metadata.get("git_hotspots", []),
            } if self.project_graph.evolution_events else {},
            "business_rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "source_files": r.source_files,
                    "rule_type": r.rule_type,
                    "priority": r.priority,
                    "metadata": r.metadata,
                }
                for r in self.project_graph.business_rules
            ] if self.project_graph.business_rules else [],
        }

        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data