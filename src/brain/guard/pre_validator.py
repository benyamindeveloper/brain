"""Pre-Execution Validation Engine for AI Guard."""

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brain.models.core import (
    ArchitectureLayer,
    ClassEntity,
    FileEntity,
    FunctionEntity,
)


class ValidationSeverity(str, Enum):
    """Validation severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationType(str, Enum):
    """Types of validation checks."""
    DUPLICATE_DETECTION = "duplicate_detection"
    ARCHITECTURE_RULE = "architecture_rule"
    BUSINESS_RULE = "business_rule"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    NAMING_CONVENTION = "naming_convention"
    SECURITY = "security"


@dataclass
class ValidationIssue:
    """Represents a validation issue found during pre-execution checks."""
    validation_type: ValidationType
    severity: ValidationSeverity
    message: str
    file_path: str | None = None
    line_number: int | None = None
    component_name: str | None = None
    existing_component: str | None = None
    rule_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.validation_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "component_name": self.component_name,
            "existing_component": self.existing_component,
            "rule_reference": self.rule_reference,
            "metadata": self.metadata,
        }


@dataclass
class ValidationResult:
    """Result of a validation run."""
    issues: list[ValidationIssue] = field(default_factory=list)
    passed: bool = True

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        if issue.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL):
            self.passed = False

    def get_errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)]

    def get_warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.issues),
            "critical": len([i for i in self.issues if i.severity == ValidationSeverity.CRITICAL]),
            "errors": len([i for i in self.issues if i.severity == ValidationSeverity.ERROR]),
            "warnings": len([i for i in self.issues if i.severity == ValidationSeverity.WARNING]),
            "info": len([i for i in self.issues if i.severity == ValidationSeverity.INFO]),
        }


class PreExecutionValidator:
    """Validates AI-proposed changes before execution."""

    def __init__(self, project_graph=None):
        self.project_graph = project_graph
        self._build_indices()

    def set_project_graph(self, project_graph):
        """Update project graph and rebuild indices."""
        self.project_graph = project_graph
        self._build_indices()

    def _build_indices(self):
        """Build lookup indices for fast validation."""
        self.class_names: dict[str, ClassEntity] = {}
        self.function_names: dict[str, FunctionEntity] = {}
        self.file_paths: dict[str, FileEntity] = {}
        self.import_map: dict[str, set[str]] = defaultdict(set)

        if not self.project_graph:
            return

        for cls in self.project_graph.classes.values():
            self.class_names[cls.name.lower()] = cls
            self.class_names[cls.qualified_name.lower()] = cls

        for func in self.project_graph.functions.values():
            self.function_names[func.name.lower()] = func
            self.function_names[func.qualified_name.lower()] = func

        for file_entity in self.project_graph.files.values():
            self.file_paths[file_entity.relative_path] = file_entity

        # Build import map
        for dep in self.project_graph.dependencies:
            self.import_map[dep.source].add(dep.target)

    def validate_proposed_class(self, class_name: str, file_path: str,
                                base_classes: list[str] = None,
                                methods: list[str] = None) -> ValidationResult:
        """Validate a proposed new class."""
        result = ValidationResult()
        class_name_lower = class_name.lower()

        # Check for duplicate class name (case-insensitive)
        if class_name_lower in self.class_names:
            existing = self.class_names[class_name_lower]
            result.add_issue(ValidationIssue(
                validation_type=ValidationType.DUPLICATE_DETECTION,
                severity=ValidationSeverity.ERROR,
                message=f"Class '{class_name}' already exists",
                file_path=file_path,
                component_name=class_name,
                existing_component=existing.qualified_name,
                rule_reference="DUP-001"
            ))

        # Check for similar names (potential confusion)
        similar = self._find_similar_names(class_name_lower, self.class_names.keys())
        for sim in similar:
            existing = self.class_names[sim]
            result.add_issue(ValidationIssue(
                validation_type=ValidationType.DUPLICATE_DETECTION,
                severity=ValidationSeverity.WARNING,
                message=f"Class name '{class_name}' is similar to existing '{existing.name}'",
                file_path=file_path,
                component_name=class_name,
                existing_component=existing.qualified_name,
                rule_reference="DUP-002"
            ))

        # Validate base classes exist
        if base_classes:
            for base in base_classes:
                if base.lower() not in self.class_names:
                    result.add_issue(ValidationIssue(
                        validation_type=ValidationType.DEPENDENCY_CONFLICT,
                        severity=ValidationSeverity.WARNING,
                        message=f"Base class '{base}' not found in project",
                        file_path=file_path,
                        component_name=class_name,
                        rule_reference="DEP-001"
                    ))

        return result

    def validate_proposed_function(self, function_name: str, file_path: str,
                                   class_name: str | None = None,
                                   parameters: list[str] = None) -> ValidationResult:
        """Validate a proposed new function/method."""
        result = ValidationResult()
        func_key = f"{class_name}.{function_name}" if class_name else function_name
        func_key_lower = func_key.lower()

        # Check for duplicate function
        if func_key_lower in self.function_names:
            existing = self.function_names[func_key_lower]
            result.add_issue(ValidationIssue(
                validation_type=ValidationType.DUPLICATE_DETECTION,
                severity=ValidationSeverity.ERROR,
                message=f"Function '{func_key}' already exists",
                file_path=file_path,
                component_name=func_key,
                existing_component=existing.qualified_name,
                rule_reference="DUP-003"
            ))

        # Check for similar names
        similar = self._find_similar_names(func_key_lower, self.function_names.keys())
        for sim in similar:
            existing = self.function_names[sim]
            result.add_issue(ValidationIssue(
                validation_type=ValidationType.DUPLICATE_DETECTION,
                severity=ValidationSeverity.WARNING,
                message=f"Function name '{func_key}' is similar to existing '{existing.name}'",
                file_path=file_path,
                component_name=func_key,
                existing_component=existing.qualified_name,
                rule_reference="DUP-004"
            ))

        return result

    def validate_proposed_import(self, source_file: str, import_path: str) -> ValidationResult:
        """Validate a proposed new import."""
        result = ValidationResult()

        # Check if import creates circular dependency
        if self._would_create_cycle(source_file, import_path):
            result.add_issue(ValidationIssue(
                validation_type=ValidationType.DEPENDENCY_CONFLICT,
                severity=ValidationSeverity.ERROR,
                message=f"Import '{import_path}' would create circular dependency",
                file_path=source_file,
                rule_reference="DEP-002"
            ))

        # Check architecture layer violation
        violation = self._check_layer_violation(source_file, import_path)
        if violation:
            result.add_issue(ValidationIssue(
                validation_type=ValidationType.ARCHITECTURE_RULE,
                severity=ValidationSeverity.ERROR,
                message=f"Import violates architecture layer rule: {violation}",
                file_path=source_file,
                rule_reference="ARCH-001"
            ))

        return result

    def validate_architecture_rules(self, file_path: str,
                                    new_imports: list[str] = None,
                                    new_exports: list[str] = None) -> ValidationResult:
        """Validate architecture rules for a file."""
        result = ValidationResult()

        if not self.project_graph:
            return result

        source_file = self.file_paths.get(file_path)
        if not source_file:
            return result

        source_layer = source_file.architecture_layer
        if source_layer == ArchitectureLayer.UNKNOWN:
            return result

        # Check imports against layer rules
        if new_imports:
            for imp in new_imports:
                target_file = self.file_paths.get(imp)
                if target_file:
                    target_layer = target_file.architecture_layer
                    if target_layer != ArchitectureLayer.UNKNOWN:
                        if not self._is_allowed_dependency(source_layer, target_layer):
                            result.add_issue(ValidationIssue(
                                validation_type=ValidationType.ARCHITECTURE_RULE,
                                severity=ValidationSeverity.ERROR,
                                message=f"Layer violation: {source_layer.value} cannot import from {target_layer.value}",
                                file_path=file_path,
                                rule_reference=f"ARCH-{source_layer.value.upper()}-{target_layer.value.upper()}"
                            ))

        return result

    def validate_business_rules(self, file_path: str,
                                changes: dict[str, Any]) -> ValidationResult:
        """Validate business rules compliance."""
        result = ValidationResult()

        if not self.project_graph:
            return result

        # Find business rules related to this file
        relevant_rules = [
            rule for rule in self.project_graph.business_rules
            if file_path in rule.source_files
        ]

        for rule in relevant_rules:
            # Simple validation - check if changes violate rule constraints
            violation = self._check_business_rule(rule, changes)
            if violation:
                result.add_issue(ValidationIssue(
                    validation_type=ValidationType.BUSINESS_RULE,
                    severity=ValidationSeverity.ERROR if rule.priority <= 2 else ValidationSeverity.WARNING,
                    message=f"Business rule violation: {violation}",
                    file_path=file_path,
                    component_name=rule.name,
                    rule_reference=rule.id
                ))

        return result

    def run_full_validation(self, proposed_changes: dict[str, Any]) -> ValidationResult:
        """Run all validations for proposed changes."""
        result = ValidationResult()

        # Validate each proposed change
        for change in proposed_changes.get("classes", []):
            r = self.validate_proposed_class(
                change["name"], change["file_path"],
                change.get("base_classes"), change.get("methods")
            )
            result.issues.extend(r.issues)

        for change in proposed_changes.get("functions", []):
            r = self.validate_proposed_function(
                change["name"], change["file_path"],
                change.get("class_name"), change.get("parameters")
            )
            result.issues.extend(r.issues)

        for change in proposed_changes.get("imports", []):
            r = self.validate_proposed_import(change["source_file"], change["import_path"])
            result.issues.extend(r.issues)

        # Architecture validation
        for file_path, imports in proposed_changes.get("imports_by_file", {}).items():
            r = self.validate_architecture_rules(file_path, new_imports=imports)
            result.issues.extend(r.issues)

        # Business rule validation
        for file_path, changes in proposed_changes.get("file_changes", {}).items():
            r = self.validate_business_rules(file_path, changes)
            result.issues.extend(r.issues)

        return result

    def _find_similar_names(self, name: str, candidates: set[str], threshold: float = 0.8) -> list[str]:
        """Find similar names using simple edit distance."""
        from difflib import SequenceMatcher
        similar = []
        for candidate in candidates:
            if candidate != name:
                ratio = SequenceMatcher(None, name, candidate).ratio()
                if ratio >= threshold:
                    similar.append(candidate)
        return similar

    def _would_create_cycle(self, source: str, target: str) -> bool:
        """Check if adding an import would create a cycle."""
        # Simple check: if target already imports source (transitively)
        visited = set()
        stack = [target]

        while stack:
            current = stack.pop()
            if current == source:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.import_map.get(current, []))

        return False

    def _check_layer_violation(self, source_file: str, import_path: str) -> str | None:
        """Check if import violates layer rules."""
        source = self.file_paths.get(source_file)
        target = self.file_paths.get(import_path)

        if not source or not target:
            return None

        source_layer = source.architecture_layer
        target_layer = target.architecture_layer

        if source_layer == ArchitectureLayer.UNKNOWN or target_layer == ArchitectureLayer.UNKNOWN:
            return None

        if not self._is_allowed_dependency(source_layer, target_layer):
            return f"{source_layer.value} -> {target_layer.value}"

        return None

    def _is_allowed_dependency(self, source: ArchitectureLayer, target: ArchitectureLayer) -> bool:
        """Check if source layer can depend on target layer (Clean Architecture rules)."""
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

        if source == target:
            return True  # Same layer allowed

        allowed = rules.get(source, [])
        return target in allowed

    def _check_business_rule(self, rule: Any, changes: dict[str, Any]) -> str | None:
        """Check if changes violate a business rule."""
        # Simple implementation - check if rule description mentions something that changes affect
        # In a full implementation, this would be more sophisticated
        return None
