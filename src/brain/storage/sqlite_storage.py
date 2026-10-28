"""SQLite storage schema and operations for Project Brain."""

import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from contextlib import contextmanager

from brain.models.core import (
    FileEntity, ClassEntity, FunctionEntity, DependencyEntity,
    ArchitectureLayerEntity, BusinessRuleEntity, EvolutionEventEntity,
    GitHistory, ArchitectureLayer, Language, ProjectGraph, DependencyGraph, ArchitectureAnalysis
)
from brain.cognitive.core import (
    SemanticTriple, TripleType, KnowledgeGraph, VectorEmbeddingManager, CognitiveProjectModel
)
from brain.cognitive.memory_layers import MemoryLayerManager, MemoryLayerType


SCHEMA_SQL = """
-- Files table
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT UNIQUE NOT NULL,
    absolute_path TEXT NOT NULL,
    language TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    lines_of_code INTEGER DEFAULT 0,
    architecture_layer TEXT DEFAULT 'unknown',
    last_modified REAL,
    git_commits_count INTEGER DEFAULT 0,
    git_authors TEXT,  -- JSON array
    git_change_frequency REAL DEFAULT 0.0,
    git_major_refactors TEXT,  -- JSON array
    imports TEXT,  -- JSON array
    exports TEXT,  -- JSON array
    classes TEXT,  -- JSON array of qualified names
    functions TEXT,  -- JSON array of qualified names
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Classes table
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT UNIQUE NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    base_classes TEXT,  -- JSON array
    implemented_interfaces TEXT,  -- JSON array
    decorators TEXT,  -- JSON array
    is_abstract BOOLEAN DEFAULT 0,
    is_interface BOOLEAN DEFAULT 0,
    docstring TEXT,
    methods TEXT,  -- JSON array
    properties TEXT,  -- JSON array
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Functions table
CREATE TABLE IF NOT EXISTS functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    class_id INTEGER,  -- NULL for module-level functions
    name TEXT NOT NULL,
    qualified_name TEXT UNIQUE NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    parameters TEXT,  -- JSON array
    return_type TEXT,
    decorators TEXT,  -- JSON array
    is_async BOOLEAN DEFAULT 0,
    is_method BOOLEAN DEFAULT 0,
    docstring TEXT,
    complexity INTEGER DEFAULT 1,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

-- Dependencies table
CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id INTEGER NOT NULL,
    target_file_id INTEGER,
    target_external TEXT,  -- For external deps
    dependency_type TEXT NOT NULL,  -- import, inheritance, composition, call
    strength REAL DEFAULT 1.0,
    metadata TEXT,  -- JSON
    created_at REAL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (source_file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Architecture layers table
CREATE TABLE IF NOT EXISTS architecture_layers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    allowed_dependencies TEXT,  -- JSON array of layer names
    forbidden_dependencies TEXT,  -- JSON array of layer names
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Architecture layer assignments (file -> layer)
CREATE TABLE IF NOT EXISTS file_architecture_layers (
    file_id INTEGER NOT NULL,
    layer_id INTEGER NOT NULL,
    PRIMARY KEY (file_id, layer_id),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (layer_id) REFERENCES architecture_layers(id) ON DELETE CASCADE
);

-- Business rules table
CREATE TABLE IF NOT EXISTS business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT UNIQUE NOT NULL,  -- BR-0001 format
    name TEXT NOT NULL,
    description TEXT,
    rule_type TEXT NOT NULL,  -- validation, invariant, constraint, workflow
    priority INTEGER DEFAULT 2,
    source_files TEXT,  -- JSON array
    metadata TEXT,  -- JSON
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Evolution events table
CREATE TABLE IF NOT EXISTS evolution_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_hash TEXT UNIQUE NOT NULL,
    timestamp REAL NOT NULL,
    author TEXT NOT NULL,
    message TEXT NOT NULL,
    files_changed TEXT,  -- JSON array
    event_type TEXT NOT NULL,  -- feature, fix, refactor, docs, test, chore, other
    impact_score REAL DEFAULT 0.0,
    related_issues TEXT,  -- JSON array
    created_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Project metadata table
CREATE TABLE IF NOT EXISTS project_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Semantic triples table (12.1)
CREATE TABLE IF NOT EXISTS semantic_triples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    metadata TEXT,  -- JSON
    created_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Vector embeddings table (12.1.2)
CREATE TABLE IF NOT EXISTS vector_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT UNIQUE NOT NULL,
    embedding TEXT NOT NULL,  -- JSON array of floats
    dimension INTEGER NOT NULL,
    model_name TEXT,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Memory layers table (12.2)
CREATE TABLE IF NOT EXISTS memory_layers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer_type TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    entity_count INTEGER DEFAULT 0,
    triple_count INTEGER DEFAULT 0,
    metadata TEXT,  -- JSON
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Layer triples mapping (which triples belong to which layer)
CREATE TABLE IF NOT EXISTS layer_triples (
    layer_id INTEGER NOT NULL,
    triple_id INTEGER NOT NULL,
    PRIMARY KEY (layer_id, triple_id),
    FOREIGN KEY (layer_id) REFERENCES memory_layers(id) ON DELETE CASCADE,
    FOREIGN KEY (triple_id) REFERENCES semantic_triples(id) ON DELETE CASCADE
);

-- Knowledge graph metadata
CREATE TABLE IF NOT EXISTS knowledge_graph_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Project metadata table
CREATE TABLE IF NOT EXISTS project_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_path ON files(relative_path);
CREATE INDEX IF NOT EXISTS idx_classes_file ON classes(file_id);
CREATE INDEX IF NOT EXISTS idx_classes_qualified ON classes(qualified_name);
CREATE INDEX IF NOT EXISTS idx_functions_file ON functions(file_id);
CREATE INDEX IF NOT EXISTS idx_functions_class ON functions(class_id);
CREATE INDEX IF NOT EXISTS idx_functions_qualified ON functions(qualified_name);
CREATE INDEX IF NOT EXISTS idx_dependencies_source ON dependencies(source_file_id);
CREATE INDEX IF NOT EXISTS idx_dependencies_target ON dependencies(target_file_id);
CREATE INDEX IF NOT EXISTS idx_evolution_commit ON evolution_events(commit_hash);
CREATE INDEX IF NOT EXISTS idx_evolution_timestamp ON evolution_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_business_rules_type ON business_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_semantic_triples_subject ON semantic_triples(subject);
CREATE INDEX IF NOT EXISTS idx_semantic_triples_predicate ON semantic_triples(predicate);
CREATE INDEX IF NOT EXISTS idx_semantic_triples_object ON semantic_triples(object);
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_entity ON vector_embeddings(entity_id);
"""


class SQLiteStorage:
    """SQLite-based persistent storage for Project Brain."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database with schema."""
        with self._get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor

    def _fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch single row."""
        with self._get_connection() as conn:
            return conn.execute(query, params).fetchone()

    def _fetchall(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows."""
        with self._get_connection() as conn:
            return conn.execute(query, params).fetchall()

    # ==================== File Operations ====================

    def upsert_file(self, file_entity: FileEntity) -> int:
        """Insert or update a file entity. Returns file_id."""
        git_history = file_entity.git_history
        git_authors = json.dumps(git_history.authors) if git_history else "[]"
        git_refactors = json.dumps(git_history.major_refactors) if git_history else "[]"
        git_commits = git_history.commits_count if git_history else 0
        git_freq = git_history.change_frequency if git_history else 0.0

        now = datetime.now().timestamp()

        self._execute("""
            INSERT INTO files (relative_path, absolute_path, language, size_bytes, lines_of_code,
                              architecture_layer, last_modified, git_commits_count, git_authors,
                              git_change_frequency, git_major_refactors, imports, exports, classes, functions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relative_path) DO UPDATE SET
                absolute_path = excluded.absolute_path,
                language = excluded.language,
                size_bytes = excluded.size_bytes,
                lines_of_code = excluded.lines_of_code,
                architecture_layer = excluded.architecture_layer,
                last_modified = excluded.last_modified,
                git_commits_count = excluded.git_commits_count,
                git_authors = excluded.git_authors,
                git_change_frequency = excluded.git_change_frequency,
                git_major_refactors = excluded.git_major_refactors,
                imports = excluded.imports,
                exports = excluded.exports,
                classes = excluded.classes,
                functions = excluded.functions,
                updated_at = excluded.updated_at
        """, (
            file_entity.relative_path,
            str(file_entity.path),
            file_entity.language.value,
            file_entity.size_bytes,
            file_entity.lines_of_code,
            file_entity.architecture_layer.value,
            file_entity.last_modified,
            git_commits,
            git_authors,
            git_freq,
            git_refactors,
            json.dumps(file_entity.imports),
            json.dumps(file_entity.exports),
            json.dumps(file_entity.classes),
            json.dumps(file_entity.functions),
            now
        ))

        # Fetch the ID after upsert
        row = self._fetchone("SELECT id FROM files WHERE relative_path = ?", (file_entity.relative_path,))
        return row[0] if row else 0

    def get_file_id(self, relative_path: str) -> Optional[int]:
        """Get file ID by relative path."""
        row = self._fetchone("SELECT id FROM files WHERE relative_path = ?", (relative_path,))
        return row[0] if row else None

    def get_file(self, file_id: int) -> Optional[FileEntity]:
        """Get file entity by ID."""
        row = self._fetchone("""
            SELECT * FROM files WHERE id = ?
        """, (file_id,))
        if not row:
            return None

        git_history = None
        if row["git_commits_count"] > 0:
            git_history = GitHistory(
                commits_count=row["git_commits_count"],
                authors=json.loads(row["git_authors"]),
                last_change=row["last_modified"],
                change_frequency=row["git_change_frequency"],
                major_refactors=json.loads(row["git_major_refactors"])
            )

        return FileEntity(
            path=Path(row["absolute_path"]),
            relative_path=row["relative_path"],
            language=Language(row["language"]),
            size_bytes=row["size_bytes"],
            lines_of_code=row["lines_of_code"],
            architecture_layer=ArchitectureLayer(row["architecture_layer"]),
            last_modified=row["last_modified"],
            git_history=git_history
        )

    def get_all_files(self) -> List[FileEntity]:
        """Get all file entities."""
        rows = self._fetchall("SELECT * FROM files")
        files = []
        for row in rows:
            git_history = None
            if row["git_commits_count"] > 0:
                git_history = GitHistory(
                    commits_count=row["git_commits_count"],
                    authors=json.loads(row["git_authors"]),
                    last_change=row["last_modified"],
                    change_frequency=row["git_change_frequency"],
                    major_refactors=json.loads(row["git_major_refactors"])
                )
            files.append(FileEntity(
                path=Path(row["absolute_path"]),
                relative_path=row["relative_path"],
                language=Language(row["language"]),
                size_bytes=row["size_bytes"],
                lines_of_code=row["lines_of_code"],
                architecture_layer=ArchitectureLayer(row["architecture_layer"]),
                last_modified=row["last_modified"],
                git_history=git_history
            ))
        return files

    # ==================== Class Operations ====================

    def upsert_class(self, class_entity: ClassEntity, file_id: int) -> int:
        """Insert or update a class entity. Returns class_id."""
        now = datetime.now().timestamp()

        self._execute("""
            INSERT INTO classes (file_id, name, qualified_name, line_start, line_end,
                               base_classes, implemented_interfaces, decorators,
                               is_abstract, is_interface, docstring, methods, properties, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qualified_name) DO UPDATE SET
                file_id = excluded.file_id,
                name = excluded.name,
                line_start = excluded.line_start,
                line_end = excluded.line_end,
                base_classes = excluded.base_classes,
                implemented_interfaces = excluded.implemented_interfaces,
                decorators = excluded.decorators,
                is_abstract = excluded.is_abstract,
                is_interface = excluded.is_interface,
                docstring = excluded.docstring,
                methods = excluded.methods,
                properties = excluded.properties,
                updated_at = excluded.updated_at
        """, (
            file_id,
            class_entity.name,
            class_entity.qualified_name,
            class_entity.line_start,
            class_entity.line_end,
            json.dumps(class_entity.base_classes),
            json.dumps(class_entity.implemented_interfaces),
            json.dumps(class_entity.decorators),
            1 if class_entity.is_abstract else 0,
            1 if class_entity.is_interface else 0,
            class_entity.docstring,
            json.dumps(class_entity.methods),
            json.dumps(class_entity.properties),
            now
        ))

        # Fetch the ID after upsert
        row = self._fetchone("SELECT id FROM classes WHERE qualified_name = ?", (class_entity.qualified_name,))
        return row[0] if row else 0

    def get_class(self, class_id: int) -> Optional[ClassEntity]:
        """Get class entity by ID."""
        row = self._fetchone("SELECT * FROM classes WHERE id = ?", (class_id,))
        if not row:
            return None
        return ClassEntity(
            name=row["name"],
            qualified_name=row["qualified_name"],
            file_path=row["file_id"],  # Will be resolved later
            line_start=row["line_start"],
            line_end=row["line_end"],
            base_classes=json.loads(row["base_classes"]),
            implemented_interfaces=json.loads(row["implemented_interfaces"]),
            decorators=json.loads(row["decorators"]),
            is_abstract=bool(row["is_abstract"]),
            is_interface=bool(row["is_interface"]),
            docstring=row["docstring"],
            methods=json.loads(row["methods"]),
            properties=json.loads(row["properties"])
        )

    def get_classes_by_file(self, file_id: int) -> List[ClassEntity]:
        """Get all classes for a file."""
        rows = self._fetchall("SELECT * FROM classes WHERE file_id = ?", (file_id,))
        classes = []
        for row in rows:
            classes.append(ClassEntity(
                name=row["name"],
                qualified_name=row["qualified_name"],
                file_path=str(file_id),
                line_start=row["line_start"],
                line_end=row["line_end"],
                base_classes=json.loads(row["base_classes"]),
                implemented_interfaces=json.loads(row["implemented_interfaces"]),
                decorators=json.loads(row["decorators"]),
                is_abstract=bool(row["is_abstract"]),
                is_interface=bool(row["is_interface"]),
                docstring=row["docstring"],
                methods=json.loads(row["methods"]),
                properties=json.loads(row["properties"])
            ))
        return classes

    # ==================== Function Operations ====================

    def upsert_function(self, func_entity: FunctionEntity, file_id: int, class_id: Optional[int] = None) -> int:
        """Insert or update a function entity. Returns function_id."""
        now = datetime.now().timestamp()

        self._execute("""
            INSERT INTO functions (file_id, class_id, name, qualified_name, line_start, line_end,
                                 parameters, return_type, decorators, is_async, is_method,
                                 docstring, complexity, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qualified_name) DO UPDATE SET
                file_id = excluded.file_id,
                class_id = excluded.class_id,
                name = excluded.name,
                line_start = excluded.line_start,
                line_end = excluded.line_end,
                parameters = excluded.parameters,
                return_type = excluded.return_type,
                decorators = excluded.decorators,
                is_async = excluded.is_async,
                is_method = excluded.is_method,
                docstring = excluded.docstring,
                complexity = excluded.complexity,
                updated_at = excluded.updated_at
        """, (
            file_id,
            class_id,
            func_entity.name,
            func_entity.qualified_name,
            func_entity.line_start,
            func_entity.line_end,
            json.dumps(func_entity.parameters),
            func_entity.return_type,
            json.dumps(func_entity.decorators),
            1 if func_entity.is_async else 0,
            1 if func_entity.is_method else 0,
            func_entity.docstring,
            func_entity.complexity,
            now
        ))

        # Fetch the ID after upsert
        row = self._fetchone("SELECT id FROM functions WHERE qualified_name = ?", (func_entity.qualified_name,))
        return row[0] if row else 0

    def get_functions_by_file(self, file_id: int) -> List[FunctionEntity]:
        """Get all functions for a file."""
        rows = self._fetchall("SELECT * FROM functions WHERE file_id = ?", (file_id,))
        functions = []
        for row in rows:
            functions.append(FunctionEntity(
                name=row["name"],
                qualified_name=row["qualified_name"],
                file_path=str(file_id),
                line_start=row["line_start"],
                line_end=row["line_end"],
                parameters=json.loads(row["parameters"]),
                return_type=row["return_type"],
                decorators=json.loads(row["decorators"]),
                is_async=bool(row["is_async"]),
                is_method=bool(row["is_method"]),
                docstring=row["docstring"],
                complexity=row["complexity"]
            ))
        return functions

    def get_functions_by_class(self, class_id: int) -> List[FunctionEntity]:
        """Get all methods for a class."""
        rows = self._fetchall("SELECT * FROM functions WHERE class_id = ?", (class_id,))
        functions = []
        for row in rows:
            functions.append(FunctionEntity(
                name=row["name"],
                qualified_name=row["qualified_name"],
                file_path=str(row["file_id"]),
                line_start=row["line_start"],
                line_end=row["line_end"],
                parameters=json.loads(row["parameters"]),
                return_type=row["return_type"],
                decorators=json.loads(row["decorators"]),
                is_async=bool(row["is_async"]),
                is_method=bool(row["is_method"]),
                docstring=row["docstring"],
                complexity=row["complexity"]
            ))
        return functions

    # ==================== Dependency Operations ====================

    def upsert_dependency(self, dep: DependencyEntity, source_file_id: int, target_file_id: Optional[int] = None) -> int:
        """Insert or update a dependency. Returns dependency_id."""
        now = datetime.now().timestamp()

        cursor = self._execute("""
            INSERT INTO dependencies (source_file_id, target_file_id, target_external,
                                    dependency_type, strength, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            source_file_id,
            target_file_id,
            dep.target if target_file_id is None else None,
            dep.dependency_type,
            dep.strength,
            json.dumps(dep.metadata),
            now
        ))
        return cursor.lastrowid

    def get_dependencies_by_source(self, source_file_id: int) -> List[DependencyEntity]:
        """Get all dependencies from a source file."""
        rows = self._fetchall("""
            SELECT d.*, f.relative_path as target_path
            FROM dependencies d
            LEFT JOIN files f ON d.target_file_id = f.id
            WHERE d.source_file_id = ?
        """, (source_file_id,))

        deps = []
        for row in rows:
            target = row["target_path"] if row["target_path"] else row["target_external"]
            deps.append(DependencyEntity(
                source=str(source_file_id),
                target=target,
                dependency_type=row["dependency_type"],
                strength=row["strength"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {}
            ))
        return deps

    # ==================== Architecture Layer Operations ====================

    def upsert_architecture_layer(self, layer_entity: ArchitectureLayerEntity) -> int:
        """Insert or update architecture layer. Returns layer_id."""
        now = datetime.now().timestamp()

        self._execute("""
            INSERT INTO architecture_layers (name, description, allowed_dependencies, forbidden_dependencies, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                allowed_dependencies = excluded.allowed_dependencies,
                forbidden_dependencies = excluded.forbidden_dependencies,
                updated_at = excluded.updated_at
        """, (
            layer_entity.name.value,
            layer_entity.description,
            json.dumps([l.value for l in layer_entity.allowed_dependencies]),
            json.dumps([l.value for l in layer_entity.forbidden_dependencies]),
            now
        ))

        # Fetch the ID after upsert
        row = self._fetchone("SELECT id FROM architecture_layers WHERE name = ?", (layer_entity.name.value,))
        return row[0] if row else 0

    def get_architecture_layer_id(self, layer_name: ArchitectureLayer) -> Optional[int]:
        """Get layer ID by name."""
        row = self._fetchone("SELECT id FROM architecture_layers WHERE name = ?", (layer_name.value,))
        return row[0] if row else None

    def assign_file_to_layer(self, file_id: int, layer_id: int):
        """Assign file to architecture layer."""
        self._execute("""
            INSERT OR REPLACE INTO file_architecture_layers (file_id, layer_id)
            VALUES (?, ?)
        """, (file_id, layer_id))

    # ==================== Business Rule Operations ====================

    def upsert_business_rule(self, rule: BusinessRuleEntity) -> int:
        """Insert or update business rule. Returns rule_id."""
        now = datetime.now().timestamp()

        cursor = self._execute("""
            INSERT INTO business_rules (rule_id, name, description, rule_type, priority,
                                      source_files, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                rule_type = excluded.rule_type,
                priority = excluded.priority,
                source_files = excluded.source_files,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
        """, (
            rule.id,
            rule.name,
            rule.description,
            rule.rule_type,
            rule.priority,
            json.dumps(rule.source_files),
            json.dumps(rule.metadata),
            now
        ))
        return cursor.lastrowid

    def get_business_rules(self, rule_type: Optional[str] = None) -> List[BusinessRuleEntity]:
        """Get business rules, optionally filtered by type."""
        if rule_type:
            rows = self._fetchall("SELECT * FROM business_rules WHERE rule_type = ? ORDER BY priority", (rule_type,))
        else:
            rows = self._fetchall("SELECT * FROM business_rules ORDER BY priority")

        rules = []
        for row in rows:
            rules.append(BusinessRuleEntity(
                id=row["rule_id"],
                name=row["name"],
                description=row["description"],
                source_files=json.loads(row["source_files"]),
                rule_type=row["rule_type"],
                priority=row["priority"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {}
            ))
        return rules

    # ==================== Evolution Event Operations ====================

    def upsert_evolution_event(self, event: EvolutionEventEntity) -> int:
        """Insert or update evolution event. Returns event_id."""
        cursor = self._execute("""
            INSERT INTO evolution_events (commit_hash, timestamp, author, message,
                                        files_changed, event_type, impact_score, related_issues, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(commit_hash) DO UPDATE SET
                timestamp = excluded.timestamp,
                author = excluded.author,
                message = excluded.message,
                files_changed = excluded.files_changed,
                event_type = excluded.event_type,
                impact_score = excluded.impact_score,
                related_issues = excluded.related_issues
        """, (
            event.commit_hash,
            event.timestamp,
            event.author,
            event.message,
            json.dumps(event.files_changed),
            event.event_type,
            event.impact_score,
            json.dumps(event.related_issues),
            datetime.now().timestamp()
        ))
        return cursor.lastrowid

    def get_evolution_events(self, limit: int = 100, offset: int = 0) -> List[EvolutionEventEntity]:
        """Get evolution events, most recent first."""
        rows = self._fetchall("""
            SELECT * FROM evolution_events
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        events = []
        for row in rows:
            events.append(EvolutionEventEntity(
                commit_hash=row["commit_hash"],
                timestamp=row["timestamp"],
                author=row["author"],
                message=row["message"],
                files_changed=json.loads(row["files_changed"]),
                event_type=row["event_type"],
                impact_score=row["impact_score"],
                related_issues=json.loads(row["related_issues"]) if row["related_issues"] else []
            ))
        return events

    # ==================== Project Metadata Operations ====================

    def set_metadata(self, key: str, value: Any):
        """Set project metadata."""
        self._execute("""
            INSERT INTO project_metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, json.dumps(value) if not isinstance(value, str) else value, datetime.now().timestamp()))

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get project metadata."""
        row = self._fetchone("SELECT value FROM project_metadata WHERE key = ?", (key,))
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    # ==================== Bulk Operations ====================

    def save_project_graph(self, project_graph: ProjectGraph):
        """Save entire project graph to database."""
        with self._get_connection() as conn:
            # Save files first
            file_id_map = {}
            for file_entity in project_graph.files.values():
                file_id = self.upsert_file(file_entity)
                file_id_map[file_entity.relative_path] = file_id

            # Save classes
            class_id_map = {}
            for class_entity in project_graph.classes.values():
                file_id = file_id_map.get(class_entity.file_path)
                if file_id:
                    class_id = self.upsert_class(class_entity, file_id)
                    class_id_map[class_entity.qualified_name] = class_id

            # Save functions
            for func_entity in project_graph.functions.values():
                file_id = file_id_map.get(func_entity.file_path)
                class_id = class_id_map.get(func_entity.class_name) if func_entity.class_name else None
                if file_id:
                    self.upsert_function(func_entity, file_id, class_id)

            # Save dependencies
            for dep in project_graph.dependencies:
                source_id = file_id_map.get(dep.source)
                target_id = file_id_map.get(dep.target)
                self.upsert_dependency(dep, source_id, target_id)

            # Save architecture layers
            layer_id_map = {}
            for layer_name, layer_entity in project_graph.architecture_layers.items():
                layer_id = self.upsert_architecture_layer(layer_entity)
                layer_id_map[layer_name] = layer_id

            # Assign files to layers
            for file_entity in project_graph.files.values():
                file_id = file_id_map.get(file_entity.relative_path)
                if file_id:
                    layer_id = layer_id_map.get(file_entity.architecture_layer.value)
                    if layer_id:
                        self.assign_file_to_layer(file_id, layer_id)

            # Save business rules
            for rule in project_graph.business_rules:
                self.upsert_business_rule(rule)

            # Save evolution events
            for event in project_graph.evolution_events:
                self.upsert_evolution_event(event)

            # Save metadata
            for key, value in project_graph.metadata.items():
                self.set_metadata(key, value)

            conn.commit()

    def load_project_graph(self) -> ProjectGraph:
        """Load entire project graph from database."""
        project_graph = ProjectGraph()

        # Load files
        file_rows = self._fetchall("SELECT * FROM files")
        file_id_map = {}
        for row in file_rows:
            git_history = None
            if row["git_commits_count"] > 0:
                git_history = GitHistory(
                    commits_count=row["git_commits_count"],
                    authors=json.loads(row["git_authors"]),
                    last_change=row["last_modified"],
                    change_frequency=row["git_change_frequency"],
                    major_refactors=json.loads(row["git_major_refactors"])
                )
            file_entity = FileEntity(
                path=Path(row["absolute_path"]),
                relative_path=row["relative_path"],
                language=Language(row["language"]),
                size_bytes=row["size_bytes"],
                lines_of_code=row["lines_of_code"],
                architecture_layer=ArchitectureLayer(row["architecture_layer"]),
                last_modified=row["last_modified"],
                git_history=git_history,
                imports=json.loads(row["imports"]) if row["imports"] else [],
                exports=json.loads(row["exports"]) if row["exports"] else [],
                classes=json.loads(row["classes"]) if row["classes"] else [],
                functions=json.loads(row["functions"]) if row["functions"] else [],
            )
            file_id_map[row["id"]] = file_entity
            project_graph.files[row["relative_path"]] = file_entity

        # Load classes
        class_rows = self._fetchall("""
            SELECT c.*, f.relative_path as file_relative_path
            FROM classes c
            JOIN files f ON c.file_id = f.id
        """)
        class_id_map = {}
        for row in class_rows:
            class_entity = ClassEntity(
                name=row["name"],
                qualified_name=row["qualified_name"],
                file_path=row["file_relative_path"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                base_classes=json.loads(row["base_classes"]),
                implemented_interfaces=json.loads(row["implemented_interfaces"]),
                decorators=json.loads(row["decorators"]),
                is_abstract=bool(row["is_abstract"]),
                is_interface=bool(row["is_interface"]),
                docstring=row["docstring"],
                methods=json.loads(row["methods"]),
                properties=json.loads(row["properties"])
            )
            project_graph.classes[row["qualified_name"]] = class_entity
            class_id_map[row["id"]] = row["qualified_name"]

        # Load functions
        func_rows = self._fetchall("SELECT * FROM functions")
        for row in func_rows:
            file_entity = file_id_map.get(row["file_id"])
            func_entity = FunctionEntity(
                name=row["name"],
                qualified_name=row["qualified_name"],
                file_path=file_entity.relative_path if file_entity else "",
                line_start=row["line_start"],
                line_end=row["line_end"],
                parameters=json.loads(row["parameters"]),
                return_type=row["return_type"],
                decorators=json.loads(row["decorators"]),
                is_async=bool(row["is_async"]),
                is_method=bool(row["is_method"]),
                docstring=row["docstring"],
                complexity=row["complexity"]
            )
            project_graph.functions[row["qualified_name"]] = func_entity

        # Load dependencies
        dep_rows = self._fetchall("""
            SELECT d.*, f1.relative_path as source_path, f2.relative_path as target_path
            FROM dependencies d
            LEFT JOIN files f1 ON d.source_file_id = f1.id
            LEFT JOIN files f2 ON d.target_file_id = f2.id
        """)
        for row in dep_rows:
            source = row["source_path"] or str(row["source_file_id"])
            target = row["target_path"] or row["target_external"]
            project_graph.dependencies.append(DependencyEntity(
                source=source,
                target=target,
                dependency_type=row["dependency_type"],
                strength=row["strength"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {}
            ))

        # Load architecture layers
        layer_rows = self._fetchall("SELECT * FROM architecture_layers")
        layer_id_map = {}
        for row in layer_rows:
            layer_entity = ArchitectureLayerEntity(
                name=ArchitectureLayer(row["name"]),
                description=row["description"],
                allowed_dependencies=[ArchitectureLayer(l) for l in json.loads(row["allowed_dependencies"])],
                forbidden_dependencies=[ArchitectureLayer(l) for l in json.loads(row["forbidden_dependencies"])]
            )
            project_graph.architecture_layers[row["name"]] = layer_entity
            layer_id_map[row["id"]] = row["name"]

        # Load file-layer assignments
        assignments = self._fetchall("SELECT file_id, layer_id FROM file_architecture_layers")
        for a in assignments:
            file_entity = file_id_map.get(a["file_id"])
            layer_name = layer_id_map.get(a["layer_id"])
            if file_entity and layer_name:
                file_entity.architecture_layer = ArchitectureLayer(layer_name)

        # Load business rules
        rule_rows = self._fetchall("SELECT * FROM business_rules")
        for row in rule_rows:
            project_graph.business_rules.append(BusinessRuleEntity(
                id=row["rule_id"],
                name=row["name"],
                description=row["description"],
                source_files=json.loads(row["source_files"]),
                rule_type=row["rule_type"],
                priority=row["priority"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {}
            ))

        # Load evolution events
        event_rows = self._fetchall("SELECT * FROM evolution_events ORDER BY timestamp DESC")
        for row in event_rows:
            project_graph.evolution_events.append(EvolutionEventEntity(
                commit_hash=row["commit_hash"],
                timestamp=row["timestamp"],
                author=row["author"],
                message=row["message"],
                files_changed=json.loads(row["files_changed"]),
                event_type=row["event_type"],
                impact_score=row["impact_score"],
                related_issues=json.loads(row["related_issues"]) if row["related_issues"] else []
            ))

        # Load metadata
        meta_rows = self._fetchall("SELECT key, value FROM project_metadata")
        for row in meta_rows:
            try:
                project_graph.metadata[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                project_graph.metadata[row["key"]] = row["value"]

        # Load cognitive model (KnowledgeGraph, embeddings, memory layers)
        self._load_cognitive_model(project_graph)

        return project_graph

    def _load_cognitive_model(self, project_graph: ProjectGraph):
        """Load cognitive model (KnowledgeGraph, embeddings, memory layers) from database."""
        try:
            from collections import defaultdict
            # Load semantic triples
            triple_rows = self._fetchall("SELECT * FROM semantic_triples")
            triples = []
            triple_id_map = {}
            for row in triple_rows:
                triple = SemanticTriple(
                    subject=row["subject"],
                    predicate=TripleType(row["predicate"]),
                    object=row["object"],
                    confidence=row["confidence"],
                    source=row["source"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
                triples.append(triple)
                triple_id_map[row["id"]] = triple
            
            # Load vector embeddings
            embedding_rows = self._fetchall("SELECT * FROM vector_embeddings")
            embedding_manager = VectorEmbeddingManager()
            embedding_manager.embeddings = {}
            for row in embedding_rows:
                embedding_manager.embeddings[row["entity_id"]] = json.loads(row["embedding"])
            
            # Build KnowledgeGraph
            from brain.cognitive.core import KnowledgeGraph, SemanticTripleExtractor, CognitiveProjectModel
            knowledge_graph = KnowledgeGraph()
            knowledge_graph.add_triples(triples)
            knowledge_graph.entity_embeddings = embedding_manager.embeddings
            
            # Load memory layers
            layer_rows = self._fetchall("SELECT * FROM memory_layers")
            layer_map = {}
            for row in layer_rows:
                layer_type = MemoryLayerType(row["layer_type"])
                layer_map[layer_type] = {
                    "name": row["name"],
                    "description": row["description"],
                    "entity_count": row["entity_count"],
                    "triple_count": row["triple_count"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                }
            
            # Load layer-triple mappings
            layer_triple_rows = self._fetchall("SELECT layer_id, triple_id FROM layer_triples")
            layer_triples = defaultdict(list)
            for row in layer_triple_rows:
                triple = triple_id_map.get(row["triple_id"])
                if triple:
                    layer_triples[row["layer_id"]].append(triple)
            
            # Load knowledge graph metadata
            meta_rows = self._fetchall("SELECT key, value FROM knowledge_graph_meta")
            kg_meta = {}
            for row in meta_rows:
                try:
                    kg_meta[row["key"]] = json.loads(row["value"])
                except json.JSONDecodeError:
                    kg_meta[row["key"]] = row["value"]
            
            # Create cognitive model
            cognitive_model = CognitiveProjectModel(project_graph)
            cognitive_model.knowledge_graph = knowledge_graph
            cognitive_model.embedding_manager.embeddings = embedding_manager.embeddings
            cognitive_model._built = True
            
            project_graph.metadata["cognitive_model"] = cognitive_model
            project_graph.metadata["knowledge_graph_meta"] = kg_meta
            
        except Exception as e:
            # Cognitive model loading failed, continue without it
            import traceback
            print(f"DEBUG: _load_cognitive_model failed: {e}")
            traceback.print_exc()

    def save_cognitive_model(self, project_graph: ProjectGraph, cognitive_model):
        """Save cognitive model (KnowledgeGraph, embeddings, memory layers) to database."""
        if not cognitive_model or not cognitive_model._built:
            return
        
        with self._get_connection() as conn:
            # Clear existing cognitive data
            conn.executescript("""
                DELETE FROM layer_triples;
                DELETE FROM semantic_triples;
                DELETE FROM vector_embeddings;
                DELETE FROM memory_layers;
                DELETE FROM knowledge_graph_meta;
            """)
            
            # Save semantic triples
            triple_id_map = {}
            for triple in cognitive_model.knowledge_graph.triples:
                cursor = conn.execute("""
                    INSERT INTO semantic_triples (subject, predicate, object, confidence, source, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    triple.subject,
                    triple.predicate.value,
                    triple.object,
                    triple.confidence,
                    triple.source,
                    json.dumps(triple.metadata),
                ))
                # Use triple content as key for mapping
                triple_key = (triple.subject, triple.predicate.value, triple.object)
                triple_id_map[triple_key] = cursor.lastrowid
            
            # Save vector embeddings
            for entity_id, embedding in cognitive_model.embedding_manager.embeddings.items():
                conn.execute("""
                    INSERT INTO vector_embeddings (entity_id, embedding, dimension, model_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(entity_id) DO UPDATE SET
                        embedding = excluded.embedding,
                        dimension = excluded.dimension,
                        model_name = excluded.model_name,
                        updated_at = excluded.updated_at
                """, (
                    entity_id,
                    json.dumps(embedding),
                    len(embedding),
                    cognitive_model.embedding_manager.model_name,
                ))
            
            # Save memory layers
            layer_manager = MemoryLayerManager(cognitive_model.knowledge_graph)
            layer_manager.populate_from_knowledge_graph()
            
            layer_id_map = {}
            for layer_type, layer in layer_manager.layers.items():
                cursor = conn.execute("""
                    INSERT INTO memory_layers (layer_type, name, description, entity_count, triple_count, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    layer_type.value,
                    layer.name,
                    layer.description,
                    len(layer.entities),
                    len(layer.triples),
                    json.dumps(layer.metadata),
                ))
                layer_id_map[layer_type] = cursor.lastrowid
            
            # Save layer-triple mappings
            for layer_type, layer in layer_manager.layers.items():
                layer_id = layer_id_map[layer_type]
                for triple in layer.triples:
                    triple_key = (triple.subject, triple.predicate.value, triple.object)
                    triple_id = triple_id_map.get(triple_key)
                    if triple_id:
                        conn.execute("""
                            INSERT OR IGNORE INTO layer_triples (layer_id, triple_id)
                            VALUES (?, ?)
                        """, (layer_id, triple_id))
            
            # Save knowledge graph metadata
            kg_meta = {
                "triple_count": len(cognitive_model.knowledge_graph.triples),
                "embedding_count": len(cognitive_model.embedding_manager.embeddings),
                "layer_count": len(layer_manager.layers),
                "built_at": datetime.now().isoformat(),
            }
            for key, value in kg_meta.items():
                conn.execute("""
                    INSERT INTO knowledge_graph_meta (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """, (key, json.dumps(value)))
            
            conn.commit()

    def clear_all(self):
        """Clear all data (for testing)."""
        with self._get_connection() as conn:
            conn.executescript("""
                DELETE FROM file_architecture_layers;
                DELETE FROM dependencies;
                DELETE FROM functions;
                DELETE FROM classes;
                DELETE FROM files;
                DELETE FROM architecture_layers;
                DELETE FROM business_rules;
                DELETE FROM evolution_events;
                DELETE FROM project_metadata;
            """)
            conn.commit()