"""Python AST analyzer for extracting code structure."""

import ast
from pathlib import Path
from typing import Optional

from brain.models.core import (
    FileEntity, ClassEntity, FunctionEntity, DependencyEntity,
    Language, NodeType
)


class PythonASTAnalyzer:
    """Analyzes Python source files using AST."""

    def __init__(self):
        self.current_file: Optional[FileEntity] = None
        self.current_class: Optional[str] = None
        self.classes: dict[str, ClassEntity] = {}
        self.functions: dict[str, FunctionEntity] = {}
        self.dependencies: list[DependencyEntity] = []
        self.imports: list[str] = []
        self.exports: list[str] = []

    def analyze(self, file_entity: FileEntity) -> FileEntity:
        """Analyze a Python file and populate the entity with extracted info."""
        self.current_file = file_entity
        self.classes = {}
        self.functions = {}
        self.dependencies = []
        self.imports = []
        self.exports = []

        try:
            source = file_entity.path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_entity.path))
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            file_entity.imports = []
            file_entity.exports = []
            file_entity.classes = []
            file_entity.functions = []
            return file_entity

        self._visit(tree)

        file_entity.imports = self.imports
        file_entity.exports = self.exports
        file_entity.classes = list(self.classes.keys())
        file_entity.functions = list(self.functions.keys())
        file_entity.lines_of_code = len(source.splitlines())

        return file_entity

    def _visit(self, node: ast.AST):
        """Visit AST nodes."""
        method_name = f"_visit_{node.__class__.__name__}"
        visitor = getattr(self, method_name, self._generic_visit)
        visitor(node)

    def _generic_visit(self, node: ast.AST):
        """Generic visitor for unhandled nodes."""
        for child in ast.iter_child_nodes(node):
            self._visit(child)

    def _visit_Module(self, node: ast.Module):
        """Visit module node."""
        for child in node.body:
            self._visit(child)

    def _visit_Import(self, node: ast.Import):
        """Visit import statement."""
        for alias in node.names:
            self.imports.append(alias.name)
            self.dependencies.append(DependencyEntity(
                source=self.current_file.relative_path if self.current_file else "",
                target=alias.name,
                dependency_type="import",
            ))

    def _visit_ImportFrom(self, node: ast.ImportFrom):
        """Visit from ... import statement."""
        module = node.module or ""
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imports.append(full_name)
            self.dependencies.append(DependencyEntity(
                source=self.current_file.relative_path if self.current_file else "",
                target=full_name,
                dependency_type="import",
            ))

    def _visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition."""
        qualified_name = f"{self.current_file.relative_path}:{node.name}" if self.current_file else node.name

        base_classes = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_classes.append(ast.unparse(base))

        decorators = [ast.unparse(d) for d in node.decorator_list]

        class_entity = ClassEntity(
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.current_file.relative_path if self.current_file else "",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            base_classes=base_classes,
            decorators=decorators,
            is_abstract=any(
                isinstance(b, ast.Name) and b.id == "ABC" for b in node.bases
            ),
            docstring=ast.get_docstring(node),
        )

        self.classes[qualified_name] = class_entity
        self.exports.append(node.name)

        old_class = self.current_class
        self.current_class = qualified_name

        for child in node.body:
            self._visit(child)

        self.current_class = old_class

    def _visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition."""
        self._process_function(node, is_async=False)

    def _visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit async function definition."""
        self._process_function(node, is_async=True)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool):
        """Process function/method node."""
        qualified_name = f"{self.current_file.relative_path}:{node.name}" if self.current_file else node.name

        if self.current_class:
            qualified_name = f"{self.current_class}.{node.name}"
            is_method = True
            class_name = self.current_class.split(":")[-1] if ":" in self.current_class else self.current_class
        else:
            is_method = False
            class_name = None

        args = []
        for arg in node.args.args:
            args.append(arg.arg)

        decorators = [ast.unparse(d) for d in node.decorator_list]

        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        func_entity = FunctionEntity(
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.current_file.relative_path if self.current_file else "",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            parameters=args,
            return_type=return_type,
            decorators=decorators,
            is_async=is_async,
            is_method=is_method,
            class_name=class_name,
            docstring=ast.get_docstring(node),
        )

        self.functions[qualified_name] = func_entity

        if not is_method:
            self.exports.append(node.name)

        # Visit function body for calls (simplified)
        for child in node.body:
            self._visit(child)

    def _visit_Call(self, node: ast.Call):
        """Visit function call - track dependencies."""
        if isinstance(node.func, ast.Name):
            self.dependencies.append(DependencyEntity(
                source=self.current_file.relative_path if self.current_file else "",
                target=node.func.id,
                dependency_type="call",
                strength=0.5,
            ))
        elif isinstance(node.func, ast.Attribute):
            # Method call - could track but keeping simple
            pass

        self._generic_visit(node)

    def get_classes(self) -> dict[str, ClassEntity]:
        """Get extracted classes."""
        return self.classes.copy()

    def get_functions(self) -> dict[str, FunctionEntity]:
        """Get extracted functions."""
        return self.functions.copy()

    def get_dependencies(self) -> list[DependencyEntity]:
        """Get extracted dependencies."""
        return self.dependencies.copy()