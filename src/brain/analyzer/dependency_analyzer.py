"""Dependency analyzer for building project dependency graph."""

from collections import defaultdict
from pathlib import Path
from typing import Optional

from brain.models.core import (
    FileEntity, DependencyEntity, DependencyGraph, Language
)


class DependencyAnalyzer:
    """Analyzes and builds dependency graph for the project."""

    def __init__(self):
        self.file_entities: dict[str, FileEntity] = {}
        self.dependencies: list[DependencyEntity] = []
        self.import_graph: dict[str, set[str]] = defaultdict(set)
        self.reverse_import_graph: dict[str, set[str]] = defaultdict(set)

    def add_file(self, file_entity: FileEntity):
        """Add a file entity to the analyzer."""
        self.file_entities[file_entity.relative_path] = file_entity

        for imp in file_entity.imports:
            self.import_graph[file_entity.relative_path].add(imp)
            self.reverse_import_graph[imp].add(file_entity.relative_path)

        for dep in file_entity.dependencies:
            self.dependencies.append(dep)

    def analyze(self) -> "DependencyGraph":
        """Analyze dependencies and return graph."""
        internal_deps = self._resolve_internal_dependencies()
        external_deps = self._identify_external_dependencies()
        circular_deps = self._detect_circular_dependencies()

        return DependencyGraph(
            files=self.file_entities,
            internal_dependencies=internal_deps,
            external_dependencies=external_deps,
            circular_dependencies=circular_deps,
            import_graph=dict(self.import_graph),
            reverse_import_graph=dict(self.reverse_import_graph),
        )

    def _resolve_internal_dependencies(self) -> list[DependencyEntity]:
        """Resolve imports to internal project files."""
        internal = []
        # Build module path map: "brain.models.core" -> FileEntity
        module_map = {}
        for f in self.file_entities.values():
            # Convert relative_path to module path: "src/brain/models/core.py" -> "src.brain.models.core"
            module_path = f.relative_path.replace("\\", "/").replace("/", ".").removesuffix(".py")
            module_map[module_path] = f
            # Also add without leading "src." if present
            if module_path.startswith("src."):
                module_map[module_path[4:]] = f

        for source_path, imports in self.import_graph.items():
            for imp in imports:
                # Try to resolve to internal file - handle both module imports and class/function imports
                # e.g., "brain.models.core" or "brain.models.core.SomeClass"
                resolved = self._resolve_import(source_path, imp, module_map)
                if resolved:
                    internal.append(DependencyEntity(
                        source=source_path,
                        target=resolved,
                        dependency_type="import",
                        strength=1.0,
                    ))

        return internal

    def _resolve_import(self, source_path: str, import_name: str, module_map: dict) -> Optional[str]:
        """Resolve an import to an internal file path."""
        # Direct match on module path
        if import_name in module_map:
            return module_map[import_name].relative_path

        # Try matching just the module part (e.g., "brain.models.core.ClassName" -> "brain.models.core")
        parts = import_name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            module_part = ".".join(parts[:i])
            if module_part in module_map:
                return module_map[module_part].relative_path

        # Try relative import resolution (e.g., from . import something)
        if import_name.startswith("."):
            # Get source module path
            source_file = self.file_entities.get(source_path)
            if source_file:
                source_module = source_file.relative_path.replace("\\", "/").replace("/", ".").removesuffix(".py")
                # Handle relative imports
                level = len(import_name) - len(import_name.lstrip("."))
                base_parts = source_module.split(".")[:-level]
                if import_name.lstrip("."):
                    target_module = ".".join(base_parts + [import_name.lstrip(".")])
                else:
                    target_module = ".".join(base_parts)
                if target_module in module_map:
                    return module_map[target_module].relative_path

        return None

    def _identify_external_dependencies(self) -> list[str]:
        """Identify external (third-party) dependencies."""
        external = set()
        # Build module path set
        internal_modules = set()
        for f in self.file_entities.values():
            module_path = f.relative_path.replace("\\", "/").replace("/", ".").removesuffix(".py")
            internal_modules.add(module_path)
            if module_path.startswith("src."):
                internal_modules.add(module_path[4:])

        for imports in self.import_graph.values():
            for imp in imports:
                if not self._is_internal_import(imp, internal_modules):
                    external.add(imp.split(".")[0])

        return sorted(external)

    def _is_internal_import(self, import_name: str, internal_modules: set) -> bool:
        """Check if an import is internal to the project."""
        if import_name in internal_modules:
            return True

        # Handle relative imports
        if import_name.startswith("."):
            return True  # Relative imports are internal by definition

        return False

    def _detect_circular_dependencies(self) -> list[list[str]]:
        """Detect circular dependencies using Tarjan's algorithm."""
        graph = {k: list(v) for k, v in self.import_graph.items() if k in self.file_entities}
        index = 0
        stack = []
        on_stack = set()
        indices = {}
        lowlinks = {}
        cycles = []

        def strongconnect(node: str):
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in graph:
                    continue
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1:
                    cycles.append(scc)

        for node in graph:
            if node not in indices:
                strongconnect(node)

        return cycles

    def get_dependency_stats(self, dependency_graph: "DependencyGraph" = None) -> dict:
        """Get dependency statistics."""
        total_files = len(self.file_entities)
        
        if dependency_graph:
            internal_deps = len(dependency_graph.internal_dependencies)
            external_deps = len(dependency_graph.external_dependencies)
            circular = len(dependency_graph.circular_dependencies)
            total_deps = internal_deps + external_deps
        else:
            total_deps = len(self.dependencies)
            internal_deps = len([d for d in self.dependencies if d.dependency_type == "import"])
            external_deps = total_deps - internal_deps
            circular = len(self._detect_circular_dependencies())

        return {
            "total_files": total_files,
            "total_dependencies": total_deps,
            "internal_dependencies": internal_deps,
            "external_dependencies": external_deps,
            "circular_dependency_groups": circular,
            "avg_dependencies_per_file": total_deps / total_files if total_files > 0 else 0,
        }