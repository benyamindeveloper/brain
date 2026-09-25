"""Multi-language analyzer using tree-sitter."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from brain.models.core import FileEntity, Language, ClassEntity, FunctionEntity, DependencyEntity


class BaseAnalyzer(ABC):
    """Base class for language-specific analyzers."""

    @abstractmethod
    def analyze(self, file_entity: FileEntity) -> FileEntity:
        """Analyze a file and populate the entity."""
        pass

    @abstractmethod
    def get_classes(self) -> dict[str, ClassEntity]:
        """Get extracted classes."""
        pass

    @abstractmethod
    def get_functions(self) -> dict[str, FunctionEntity]:
        """Get extracted functions."""
        pass

    @abstractmethod
    def get_dependencies(self) -> list[DependencyEntity]:
        """Get extracted dependencies."""
        pass


class TreeSitterAnalyzer(BaseAnalyzer):
    """Generic tree-sitter based analyzer."""

    def __init__(self, language: Language):
        self.language = language
        self._parser = None
        self._language = None
        self._init_parser()
        self.classes: dict[str, ClassEntity] = {}
        self.functions: dict[str, FunctionEntity] = {}
        self.dependencies: list[DependencyEntity] = []
        self.imports: list[str] = []
        self.exports: list[str] = []
        self.current_file: Optional[FileEntity] = None

    def _init_parser(self):
        """Initialize tree-sitter parser for the language."""
        try:
            from tree_sitter import Language, Parser
            import tree_sitter_python as tspython
            import tree_sitter_javascript as tsjavascript
            import tree_sitter_typescript as tstypescript

            language_map = {
                Language.PYTHON: tspython.language(),
                Language.JAVASCRIPT: tsjavascript.language(),
                Language.TYPESCRIPT: tstypescript.language_typescript(),
            }

            self._language = Language(language_map.get(self.language))
            self._parser = Parser()
            self._parser.language = self._language
        except ImportError:
            pass  # tree-sitter not available for this language

    def analyze(self, file_entity: FileEntity) -> FileEntity:
        """Analyze a file using tree-sitter."""
        self.current_file = file_entity
        self.classes = {}
        self.functions = {}
        self.dependencies = []
        self.imports = []
        self.exports = []

        if not self._parser:
            return file_entity

        try:
            source = file_entity.path.read_bytes()
            tree = self._parser.parse(source)
            self._traverse(tree.root_node, source)
        except Exception:
            pass

        file_entity.imports = self.imports
        file_entity.exports = self.exports
        file_entity.classes = list(self.classes.keys())
        file_entity.functions = list(self.functions.keys())
        file_entity.lines_of_code = len(source.splitlines())

        return file_entity

    def _traverse(self, node, source: bytes):
        """Traverse tree-sitter AST."""
        # Language-specific node type handling
        handlers = {
            "import_statement": self._handle_import,
            "import_from_statement": self._handle_import_from,
            "class_definition": self._handle_class,
            "function_definition": self._handle_function,
            "method_definition": self._handle_method,
            "call_expression": self._handle_call,
        }

        handler = handlers.get(node.type)
        if handler:
            handler(node, source)

        for child in node.children:
            self._traverse(child, source)

    def _handle_import(self, node, source: bytes):
        """Handle import statement."""
        text = source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
        self.imports.append(text.strip())

    def _handle_import_from(self, node, source: bytes):
        """Handle from ... import statement."""
        text = source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
        self.imports.append(text.strip())

    def _handle_class(self, node, source: bytes):
        """Handle class definition."""
        name_node = node.child_by_field_name("name")
        if name_node:
            name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
            qualified = f"{self.current_file.relative_path}:{name}" if self.current_file else name

            self.classes[qualified] = ClassEntity(
                name=name,
                qualified_name=qualified,
                file_path=self.current_file.relative_path if self.current_file else "",
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
            )
            self.exports.append(name)

    def _handle_function(self, node, source: bytes):
        """Handle function definition."""
        name_node = node.child_by_field_name("name")
        if name_node:
            name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
            qualified = f"{self.current_file.relative_path}:{name}" if self.current_file else name

            self.functions[qualified] = FunctionEntity(
                name=name,
                qualified_name=qualified,
                file_path=self.current_file.relative_path if self.current_file else "",
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
            )
            self.exports.append(name)

    def _handle_method(self, node, source: bytes):
        """Handle method definition."""
        self._handle_function(node, source)

    def _handle_call(self, node, source: bytes):
        """Handle function call."""
        func_node = node.child_by_field_name("function")
        if func_node and func_node.type == "identifier":
            name = source[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="ignore")
            self.dependencies.append(DependencyEntity(
                source=self.current_file.relative_path if self.current_file else "",
                target=name,
                dependency_type="call",
                strength=0.5,
            ))

    def get_classes(self) -> dict[str, ClassEntity]:
        return self.classes.copy()

    def get_functions(self) -> dict[str, FunctionEntity]:
        return self.functions.copy()

    def get_dependencies(self) -> list[DependencyEntity]:
        return self.dependencies.copy()


class AnalyzerFactory:
    """Factory for creating language-specific analyzers."""

    @staticmethod
    def create(language: Language) -> BaseAnalyzer:
        """Create analyzer for the given language."""
        if language == Language.PYTHON:
            from brain.analyzer.python_analyzer import PythonASTAnalyzer
            return PythonASTAnalyzer()
        elif language in (Language.JAVASCRIPT, Language.TYPESCRIPT):
            return TreeSitterAnalyzer(language)
        else:
            return TreeSitterAnalyzer(language)