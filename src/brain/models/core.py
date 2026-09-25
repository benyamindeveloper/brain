"""Core data models for Project Brain."""

from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class Language(str, Enum):
    """Supported programming languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    CPP = "cpp"
    PHP = "php"
    RUBY = "ruby"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    UNKNOWN = "unknown"


class ArchitectureLayer(str, Enum):
    """Standard architecture layers."""
    PRESENTATION = "presentation"
    APPLICATION = "application"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    SHARED = "shared"
    UNKNOWN = "unknown"


class NodeType(str, Enum):
    """Types of nodes in the project graph."""
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    INTERFACE = "interface"
    MODULE = "module"
    PACKAGE = "package"


class FileEntity(BaseModel):
    """Represents a source file in the project."""
    path: Path
    relative_path: str
    language: Language
    size_bytes: int
    lines_of_code: int = 0
    imports: list[str] = Field(default_factory=list)
    exports: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    dependencies: list["DependencyEntity"] = Field(default_factory=list)
    architecture_layer: ArchitectureLayer = ArchitectureLayer.UNKNOWN
    last_modified: Optional[float] = None
    git_history: Optional["GitHistory"] = None


class ClassEntity(BaseModel):
    """Represents a class/interface in the codebase."""
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    methods: list[str] = Field(default_factory=list)
    properties: list[str] = Field(default_factory=list)
    base_classes: list[str] = Field(default_factory=list)
    implemented_interfaces: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    is_abstract: bool = False
    is_interface: bool = False
    docstring: Optional[str] = None


class FunctionEntity(BaseModel):
    """Represents a function/method in the codebase."""
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    parameters: list[str] = Field(default_factory=list)
    return_type: Optional[str] = None
    decorators: list[str] = Field(default_factory=list)
    is_async: bool = False
    is_method: bool = False
    class_name: Optional[str] = None
    docstring: Optional[str] = None
    complexity: int = 1


class DependencyEntity(BaseModel):
    """Represents a dependency between components."""
    source: str
    target: str
    dependency_type: str  # import, inheritance, composition, call
    strength: float = 1.0  # 0.0 to 1.0
    metadata: dict = Field(default_factory=dict)


class ArchitectureLayerEntity(BaseModel):
    """Represents an architectural layer."""
    name: ArchitectureLayer
    description: str
    files: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    allowed_dependencies: list[ArchitectureLayer] = Field(default_factory=list)
    forbidden_dependencies: list[ArchitectureLayer] = Field(default_factory=list)


class BusinessRuleEntity(BaseModel):
    """Represents a business rule extracted from code."""
    id: str
    name: str
    description: str
    source_files: list[str] = Field(default_factory=list)
    rule_type: str  # validation, constraint, workflow, invariant
    priority: int = 1  # 1=critical, 2=high, 3=medium, 4=low
    metadata: dict = Field(default_factory=dict)


class EvolutionEventEntity(BaseModel):
    """Represents an evolution event from Git history."""
    commit_hash: str
    timestamp: float
    author: str
    message: str
    files_changed: list[str] = Field(default_factory=list)
    event_type: str  # feature, fix, refactor, chore, docs
    impact_score: float = 0.0
    related_issues: list[str] = Field(default_factory=list)


class GitHistory(BaseModel):
    """Git history summary for a file."""
    commits_count: int = 0
    authors: list[str] = Field(default_factory=list)
    last_change: Optional[float] = None
    change_frequency: float = 0.0  # changes per month
    major_refactors: list[str] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    """Dependency graph for the project."""
    files: dict[str, FileEntity] = Field(default_factory=dict)
    internal_dependencies: list[DependencyEntity] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)
    circular_dependencies: list[list[str]] = Field(default_factory=list)
    import_graph: dict[str, list[str]] = Field(default_factory=dict)
    reverse_import_graph: dict[str, list[str]] = Field(default_factory=dict)


class ArchitectureAnalysis(BaseModel):
    """Architecture analysis results."""
    layers: dict[ArchitectureLayer, ArchitectureLayerEntity] = Field(default_factory=dict)
    detected_patterns: list[str] = Field(default_factory=list)
    layer_violations: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


class ProjectGraph(BaseModel):
    """Complete project graph representation."""
    files: dict[str, FileEntity] = Field(default_factory=dict)
    classes: dict[str, ClassEntity] = Field(default_factory=dict)
    functions: dict[str, FunctionEntity] = Field(default_factory=dict)
    dependencies: list[DependencyEntity] = Field(default_factory=list)
    architecture_layers: dict[str, ArchitectureLayerEntity] = Field(default_factory=dict)
    business_rules: list[BusinessRuleEntity] = Field(default_factory=list)
    evolution_events: list[EvolutionEventEntity] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)