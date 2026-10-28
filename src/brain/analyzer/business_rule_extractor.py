"""Business rule extractor from source code."""

import ast
import re
from pathlib import Path
from typing import Optional, List, Dict, Set
from collections import defaultdict

from brain.models.core import (
    FileEntity, BusinessRuleEntity, ClassEntity, FunctionEntity, Language
)


class BusinessRuleExtractor:
    """Extracts business rules from source code patterns."""

    def __init__(self):
        self.rules: List[BusinessRuleEntity] = []
        self.rule_counter = 0

    def extract_from_file(self, file_entity: FileEntity, classes: Dict[str, ClassEntity], functions: Dict[str, FunctionEntity]) -> List[BusinessRuleEntity]:
        """Extract business rules from a single file."""
        if file_entity.language != Language.PYTHON:
            return []

        rules = []

        try:
            source = file_entity.path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_entity.path))
        except Exception:
            return []

        # Extract rules from various patterns
        rules.extend(self._extract_validation_rules(tree, file_entity, classes, functions))
        rules.extend(self._extract_invariant_rules(tree, file_entity, classes, functions))
        rules.extend(self._extract_constraint_rules(tree, file_entity, classes, functions))
        rules.extend(self._extract_workflow_rules(tree, file_entity, classes, functions))
        rules.extend(self._extract_docstring_rules(tree, file_entity, classes, functions))

        self.rules.extend(rules)
        return rules

    def _extract_validation_rules(self, tree: ast.AST, file_entity: FileEntity, classes: Dict, functions: Dict) -> List[BusinessRuleEntity]:
        """Extract validation rules (e.g., @validator, validate_*, is_valid_*)."""
        rules = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check for validation method patterns
                if self._is_validation_method(node):
                    rule = self._create_rule(
                        name=f"Validation: {node.name}",
                        description=self._get_function_description(node),
                        source_file=file_entity.relative_path,
                        rule_type="validation",
                        priority=2,
                        metadata={
                            "function": node.name,
                            "line": node.lineno,
                            "class": self._get_containing_class(node, classes),
                        }
                    )
                    rules.append(rule)

                # Check for decorators like @validator, @validates
                for decorator in node.decorator_list:
                    dec_name = self._get_decorator_name(decorator)
                    if dec_name and any(kw in dec_name.lower() for kw in ["validator", "validates", "validate"]):
                        rule = self._create_rule(
                            name=f"Validator: {node.name}",
                            description=self._get_function_description(node),
                            source_file=file_entity.relative_path,
                            rule_type="validation",
                            priority=1,
                            metadata={
                                "function": node.name,
                                "decorator": dec_name,
                                "line": node.lineno,
                                "class": self._get_containing_class(node, classes),
                            }
                        )
                        rules.append(rule)

        return rules

    def _extract_invariant_rules(self, tree: ast.AST, file_entity: FileEntity, classes: Dict, functions: Dict) -> List[BusinessRuleEntity]:
        """Extract invariant rules (e.g., __post_init__, property setters, assert statements)."""
        rules = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # __post_init__ in dataclasses
                if node.name == "__post_init__":
                    rule = self._create_rule(
                        name=f"Invariant: {self._get_containing_class(node, classes)}.__post_init__",
                        description=self._get_function_description(node) or "Post-initialization validation",
                        source_file=file_entity.relative_path,
                        rule_type="invariant",
                        priority=1,
                        metadata={
                            "function": node.name,
                            "line": node.lineno,
                            "class": self._get_containing_class(node, classes),
                        }
                    )
                    rules.append(rule)

                # Property setters with validation
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute) and decorator.attr == "setter":
                        prop_name = node.name
                        rule = self._create_rule(
                            name=f"Constraint: {self._get_containing_class(node, classes)}.{prop_name} setter",
                            description=self._get_function_description(node) or f"Setter validation for {prop_name}",
                            source_file=file_entity.relative_path,
                            rule_type="constraint",
                            priority=2,
                            metadata={
                                "property": prop_name,
                                "line": node.lineno,
                                "class": self._get_containing_class(node, classes),
                            }
                        )
                        rules.append(rule)

            # Assert statements as inline invariants
            elif isinstance(node, ast.Assert):
                rule = self._create_rule(
                    name=f"Assertion at line {node.lineno}",
                    description=ast.unparse(node) if hasattr(ast, 'unparse') else "Inline assertion",
                    source_file=file_entity.relative_path,
                    rule_type="invariant",
                    priority=3,
                    metadata={
                        "line": node.lineno,
                        "assertion": ast.unparse(node) if hasattr(ast, 'unparse') else "",
                    }
                )
                rules.append(rule)

        return rules

    def _extract_constraint_rules(self, tree: ast.AST, file_entity: FileEntity, classes: Dict, functions: Dict) -> List[BusinessRuleEntity]:
        """Extract constraint rules (e.g., field constraints, type constraints, range checks)."""
        rules = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check for field constraints in dataclasses, Pydantic models, etc.
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and item.annotation:
                        # Check for constraints in type hints or default values
                        constraint = self._extract_field_constraint(item, node.name)
                        if constraint:
                            rule = self._create_rule(
                                name=f"Constraint: {node.name}.{item.target.id if isinstance(item.target, ast.Name) else 'field'}",
                                description=constraint,
                                source_file=file_entity.relative_path,
                                rule_type="constraint",
                                priority=2,
                                metadata={
                                    "class": node.name,
                                    "field": item.target.id if isinstance(item.target, ast.Name) else "",
                                    "line": item.lineno,
                                }
                            )
                            rules.append(rule)

        return rules

    def _extract_workflow_rules(self, tree: ast.AST, file_entity: FileEntity, classes: Dict, functions: Dict) -> List[BusinessRuleEntity]:
        """Extract workflow/business process rules (e.g., state machines, order of operations)."""
        rules = []

        # Look for state machine patterns, workflow methods
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check for state machine patterns
                state_methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        if any(kw in item.name.lower() for kw in ["transition", "on_", "handle_", "process_", "execute_", "validate_"]):
                            state_methods.append(item.name)

                if len(state_methods) >= 2:
                    rule = self._create_rule(
                        name=f"Workflow: {node.name} state transitions",
                        description=f"State machine with methods: {', '.join(state_methods)}",
                        source_file=file_entity.relative_path,
                        rule_type="workflow",
                        priority=2,
                        metadata={
                            "class": node.name,
                            "methods": state_methods,
                        }
                    )
                    rules.append(rule)

        return rules

    def _extract_docstring_rules(self, tree: ast.AST, file_entity: FileEntity, classes: Dict, functions: Dict) -> List[BusinessRuleEntity]:
        """Extract business rules from docstrings (e.g., 'Business Rule: ...', 'Invariant: ...')."""
        rules = []

        rule_patterns = [
            (r"business rule[:\-]\s*(.+)", "validation", 2),
            (r"invariant[:\-]\s*(.+)", "invariant", 1),
            (r"constraint[:\-]\s*(.+)", "constraint", 2),
            (r"must (not )?(?:be|have|ensure|validate)[:\-]\s*(.+)", "validation", 2),
            (r"should (not )?(?:be|have|ensure|validate)[:\-]\s*(.+)", "validation", 3),
        ]

        # Only these node types can have docstrings
        docstring_node_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

        for node in ast.walk(tree):
            if not isinstance(node, docstring_node_types):
                continue
            docstring = ast.get_docstring(node)
            if not docstring:
                continue

            for pattern, rule_type, priority in rule_patterns:
                matches = re.finditer(pattern, docstring, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    rule_text = match.group(1).strip() if match.groups() else match.group(0).strip()
                    name = self._get_node_name(node, classes)
                    rule = self._create_rule(
                        name=f"{rule_type.title()}: {name}",
                        description=rule_text,
                        source_file=file_entity.relative_path,
                        rule_type=rule_type,
                        priority=priority,
                        metadata={
                            "source_node": type(node).__name__,
                            "node_name": name,
                            "line": node.lineno,
                        }
                    )
                    rules.append(rule)

        return rules

    def _is_validation_method(self, node: ast.FunctionDef) -> bool:
        """Check if a method is a validation method."""
        name = node.name.lower()
        validation_patterns = [
            "validate_", "is_valid", "check_", "verify_", "ensure_",
            "assert_", "confirm_", "validate"
        ]
        return any(name.startswith(p) or name == p for p in validation_patterns)

    def _get_decorator_name(self, decorator: ast.AST) -> Optional[str]:
        """Get decorator name as string."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        elif isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)
        return None

    def _get_containing_class(self, node: ast.AST, classes: Dict) -> Optional[str]:
        """Find the class containing this node."""
        # Walk up the AST to find class
        for class_entity in classes.values():
            if class_entity.file_path == getattr(node, 'file_path', ''):
                if class_entity.line_start <= node.lineno <= class_entity.line_end:
                    return class_entity.name
        return None

    def _get_function_description(self, node: ast.FunctionDef) -> Optional[str]:
        """Get function description from docstring or body."""
        docstring = ast.get_docstring(node)
        if docstring:
            return docstring.strip()[:200]
        return None

    def _extract_field_constraint(self, node: ast.AnnAssign, class_name: str) -> Optional[str]:
        """Extract constraint from annotated assignment."""
        if not isinstance(node.target, ast.Name):
            return None

        field_name = node.target.id
        annotation = ast.unparse(node.annotation) if hasattr(ast, 'unparse') else ""

        # Look for common constraint patterns
        constraints = []
        if "Annotated" in annotation:
            constraints.append(f"Annotated type with constraints: {annotation}")
        if node.value:
            # Check for Field(), validator(), etc.
            value_str = ast.unparse(node.value) if hasattr(ast, 'unparse') else ""
            if any(kw in value_str for kw in ["Field", "validator", "const", "gt", "lt", "ge", "le", "min", "max"]):
                constraints.append(f"Field constraint: {value_str}")

        return "; ".join(constraints) if constraints else None

    def _get_node_name(self, node: ast.AST, classes: Dict) -> str:
        """Get a readable name for the node."""
        if isinstance(node, ast.ClassDef):
            return node.name
        elif isinstance(node, ast.FunctionDef):
            cls = self._get_containing_class(node, classes)
            return f"{cls}.{node.name}" if cls else node.name
        elif isinstance(node, ast.Module):
            return "module"
        return "unknown"

    def _create_rule(self, name: str, description: str, source_file: str, rule_type: str, priority: int, metadata: Dict) -> BusinessRuleEntity:
        """Create a BusinessRuleEntity with auto-incremented ID."""
        self.rule_counter += 1
        return BusinessRuleEntity(
            id=f"BR-{self.rule_counter:04d}",
            name=name[:100],
            description=description[:500] if description else "No description",
            source_files=[source_file],
            rule_type=rule_type,
            priority=priority,
            metadata=metadata
        )

    def get_all_rules(self) -> List[BusinessRuleEntity]:
        """Get all extracted rules."""
        return self.rules.copy()

    def clear(self):
        """Clear extracted rules."""
        self.rules = []
        self.rule_counter = 0