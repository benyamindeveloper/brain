"""Architecture analyzer for detecting patterns and layers."""

from collections import defaultdict
from pathlib import Path
from typing import Optional

from brain.models.core import (
    FileEntity, ArchitectureLayer, ArchitectureLayerEntity,
    ArchitectureAnalysis, ClassEntity, FunctionEntity
)


class ArchitectureAnalyzer:
    """Analyzes project architecture and detects patterns."""

    def __init__(self):
        self.files: dict[str, FileEntity] = {}
        self.classes: dict[str, ClassEntity] = {}
        self.functions: dict[str, FunctionEntity] = {}
        self.layers: dict[ArchitectureLayer, ArchitectureLayerEntity] = {}

    def add_file(self, file_entity: FileEntity):
        """Add a file entity."""
        self.files[file_entity.relative_path] = file_entity

    def add_class(self, class_entity: ClassEntity):
        """Add a class entity."""
        self.classes[class_entity.qualified_name] = class_entity

    def add_function(self, function_entity: FunctionEntity):
        """Add a function entity."""
        self.functions[function_entity.qualified_name] = function_entity

    def analyze(self) -> ArchitectureAnalysis:
        """Analyze architecture and return results."""
        self._build_layers()
        self._detect_patterns()
        violations = self._check_layer_violations()
        metrics = self._calculate_metrics()

        return ArchitectureAnalysis(
            layers=self.layers,
            detected_patterns=self._detected_patterns,
            layer_violations=violations,
            metrics=metrics,
        )

    def _build_layers(self):
        """Build architecture layers from file entities."""
        layer_files = defaultdict(list)
        layer_classes = defaultdict(list)

        for file_entity in self.files.values():
            layer_files[file_entity.architecture_layer].append(file_entity.relative_path)

        for class_entity in self.classes.values():
            # Find the file's layer
            file_entity = self.files.get(class_entity.file_path)
            if file_entity:
                layer_classes[file_entity.architecture_layer].append(class_entity.qualified_name)

        for layer in ArchitectureLayer:
            if layer == ArchitectureLayer.UNKNOWN:
                continue

            files = layer_files.get(layer, [])
            classes = layer_classes.get(layer, [])

            # Only create layer entity if it has files or classes
            if not files and not classes:
                continue

            allowed = self._get_allowed_dependencies(layer)
            forbidden = self._get_forbidden_dependencies(layer)

            self.layers[layer] = ArchitectureLayerEntity(
                name=layer,
                description=self._get_layer_description(layer),
                files=files,
                classes=classes,
                allowed_dependencies=allowed,
                forbidden_dependencies=forbidden,
            )

    def _get_allowed_dependencies(self, layer: ArchitectureLayer) -> list[ArchitectureLayer]:
        """Get allowed dependencies for a layer (based on Clean Architecture)."""
        rules = {
            ArchitectureLayer.PRESENTATION: [
                ArchitectureLayer.APPLICATION,
                ArchitectureLayer.DOMAIN,
                ArchitectureLayer.SHARED,
            ],
            ArchitectureLayer.APPLICATION: [
                ArchitectureLayer.DOMAIN,
                ArchitectureLayer.SHARED,
            ],
            ArchitectureLayer.DOMAIN: [
                ArchitectureLayer.SHARED,
            ],
            ArchitectureLayer.INFRASTRUCTURE: [
                ArchitectureLayer.DOMAIN,
                ArchitectureLayer.APPLICATION,
                ArchitectureLayer.SHARED,
            ],
            ArchitectureLayer.SHARED: [],
        }
        return rules.get(layer, [])

    def _get_forbidden_dependencies(self, layer: ArchitectureLayer) -> list[ArchitectureLayer]:
        """Get forbidden dependencies for a layer."""
        all_layers = [l for l in ArchitectureLayer if l != ArchitectureLayer.UNKNOWN]
        allowed = self._get_allowed_dependencies(layer)
        return [l for l in all_layers if l not in allowed and l != layer]

    def _get_layer_description(self, layer: ArchitectureLayer) -> str:
        """Get description for a layer."""
        descriptions = {
            ArchitectureLayer.PRESENTATION: "UI layer - controllers, views, components, API endpoints",
            ArchitectureLayer.APPLICATION: "Application layer - use cases, services, DTOs, mappers",
            ArchitectureLayer.DOMAIN: "Domain layer - entities, value objects, aggregates, domain events",
            ArchitectureLayer.INFRASTRUCTURE: "Infrastructure layer - database, external services, frameworks",
            ArchitectureLayer.SHARED: "Shared kernel - common utilities, base classes, extensions",
        }
        return descriptions.get(layer, "Unknown layer")

    def _detect_patterns(self):
        """Detect architectural patterns."""
        self._detected_patterns = []

        # Check for Layered Architecture
        if self._has_layered_structure():
            self._detected_patterns.append("Layered Architecture")

        # Check for Clean Architecture
        if self._has_clean_architecture():
            self._detected_patterns.append("Clean Architecture")

        # Check for DDD
        if self._has_ddd_patterns():
            self._detected_patterns.append("Domain-Driven Design (DDD)")

        # Check for MVC/MVVM
        if self._has_mvc_patterns():
            self._detected_patterns.append("MVC/MVVM")

        # Check for Repository Pattern
        if self._has_repository_pattern():
            self._detected_patterns.append("Repository Pattern")

        # Check for CQRS
        if self._has_cqrs_pattern():
            self._detected_patterns.append("CQRS")

    def _has_layered_structure(self) -> bool:
        """Check if project has clear layer separation."""
        layers_present = set(f.architecture_layer for f in self.files.values())
        required = {ArchitectureLayer.PRESENTATION, ArchitectureLayer.APPLICATION, ArchitectureLayer.DOMAIN}
        return len(layers_present & required) >= 2

    def _has_clean_architecture(self) -> bool:
        """Check for Clean Architecture markers."""
        has_domain = any(f.architecture_layer == ArchitectureLayer.DOMAIN for f in self.files.values())
        has_application = any(f.architecture_layer == ArchitectureLayer.APPLICATION for f in self.files.values())
        has_infrastructure = any(f.architecture_layer == ArchitectureLayer.INFRASTRUCTURE for f in self.files.values())

        # Check for dependency rule: inner layers don't depend on outer
        return has_domain and has_application and has_infrastructure

    def _has_ddd_patterns(self) -> bool:
        """Check for DDD patterns."""
        ddd_keywords = ["entity", "aggregate", "valueobject", "repository", "specification", "domainevent"]
        class_names = " ".join(c.name.lower() for c in self.classes.values())
        return any(kw in class_names for kw in ddd_keywords)

    def _has_mvc_patterns(self) -> bool:
        """Check for MVC/MVVM patterns."""
        mvc_keywords = ["controller", "view", "model", "viewmodel", "presenter"]
        class_names = " ".join(c.name.lower() for c in self.classes.values())
        return sum(1 for kw in mvc_keywords if kw in class_names) >= 2

    def _has_repository_pattern(self) -> bool:
        """Check for Repository pattern."""
        repo_keywords = ["repository", "repo"]
        class_names = " ".join(c.name.lower() for c in self.classes.values())
        interface_names = " ".join(c.name.lower() for c in self.classes.values() if c.is_interface)
        return any(kw in class_names for kw in repo_keywords) or any(kw in interface_names for kw in repo_keywords)

    def _has_cqrs_pattern(self) -> bool:
        """Check for CQRS pattern."""
        cqrs_keywords = ["command", "query", "handler", "dispatcher"]
        class_names = " ".join(c.name.lower() for c in self.classes.values())
        return sum(1 for kw in cqrs_keywords if kw in class_names) >= 2

    def _check_layer_violations(self) -> list[dict]:
        """Check for layer dependency violations."""
        violations = []

        # Build module path map for import resolution
        module_map = {}
        for f in self.files.values():
            module_path = f.relative_path.replace("\\", "/").replace("/", ".").removesuffix(".py")
            module_map[module_path] = f
            if module_path.startswith("src."):
                module_map[module_path[4:]] = f

        for source_file in self.files.values():
            source_layer = source_file.architecture_layer
            if source_layer == ArchitectureLayer.UNKNOWN:
                continue

            allowed = self._get_allowed_dependencies(source_layer)

            for imp in source_file.imports:
                # Try to resolve import to a file
                target_file = None
                if imp in module_map:
                    target_file = module_map[imp]
                else:
                    # Try matching module part (e.g., "infrastructure.database.ClassName")
                    parts = imp.split(".")
                    for i in range(len(parts) - 1, 0, -1):
                        module_part = ".".join(parts[:i])
                        if module_part in module_map:
                            target_file = module_map[module_part]
                            break

                if not target_file:
                    continue

                target_layer = target_file.architecture_layer
                if target_layer == ArchitectureLayer.UNKNOWN:
                    continue

                if target_layer not in allowed and target_layer != source_layer:
                    violations.append({
                        "source_file": source_file.relative_path,
                        "source_layer": source_layer.value,
                        "target_file": target_file.relative_path,
                        "target_layer": target_layer.value,
                        "import": imp,
                        "severity": "high" if target_layer in self._get_forbidden_dependencies(source_layer) else "medium",
                    })

        return violations

    def _calculate_metrics(self) -> dict:
        """Calculate architecture metrics."""
        layer_counts = defaultdict(int)
        for f in self.files.values():
            layer_counts[f.architecture_layer.value] += 1

        total_files = len(self.files)
        layered_files = sum(1 for f in self.files.values() if f.architecture_layer != ArchitectureLayer.UNKNOWN)

        return {
            "total_files": total_files,
            "layered_files": layered_files,
            "layer_coverage": layered_files / total_files if total_files > 0 else 0,
            "files_per_layer": dict(layer_counts),
            "detected_patterns": self._detected_patterns,
            "violation_count": len(self._check_layer_violations()),
        }