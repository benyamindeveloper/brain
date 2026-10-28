"""Knowledge Representation - Semantic triples, vector embeddings, and graph representation (12.1)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from collections import defaultdict
import json

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except (ImportError, OSError):
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from brain.models.core import (
    FileEntity, ClassEntity, FunctionEntity, DependencyEntity,
    ArchitectureLayer, BusinessRuleEntity, EvolutionEventEntity,
    Language, ProjectGraph
)


class TripleType(str, Enum):
    """Types of semantic triples."""
    # Structural
    CONTAINS = "contains"           # file contains class/function
    DEFINES = "defines"             # class defines method
    INHERITS = "inherits"           # class inherits from class
    IMPLEMENTS = "implements"       # class implements interface
    CALLS = "calls"                 # function calls function
    IMPORTS = "imports"             # file imports module
    
    # Architectural
    BELONGS_TO_LAYER = "belongs_to_layer"
    DEPENDS_ON = "depends_on"       # layer depends on layer
    VIOLATES = "violates"           # violates architecture rule
    
    # Business
    ENFORCES = "enforces"           # rule enforces constraint
    VALIDATES = "validates"         # function validates rule
    TRIGGERS = "triggers"           # event triggers rule
    
    # Evolution
    MODIFIED_IN = "modified_in"     # entity modified in commit
    INTRODUCED_IN = "introduced_in" # entity introduced in commit
    REFACTORED_IN = "refactored_in" # entity refactored in commit
    
    # Semantic
    SIMILAR_TO = "similar_to"       # semantic similarity
    RELATED_TO = "related_to"       # general relation


@dataclass
class SemanticTriple:
    """A semantic triple (subject, predicate, object) with metadata."""
    subject: str           # URI/ID of subject
    predicate: TripleType  # relationship type
    object: str            # URI/ID of object
    confidence: float = 1.0
    source: str = ""       # source of this triple (analyzer name)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate.value,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticTriple":
        return cls(
            subject=data["subject"],
            predicate=TripleType(data["predicate"]),
            object=data["object"],
            confidence=data.get("confidence", 1.0),
            source=data.get("source", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class KnowledgeGraph:
    """Knowledge graph with semantic triples and vector embeddings."""
    triples: List[SemanticTriple] = field(default_factory=list)
    entity_embeddings: Dict[str, List[float]] = field(default_factory=dict)  # entity_id -> embedding
    entity_types: Dict[str, str] = field(default_factory=dict)  # entity_id -> type
    _nx_graph: Optional[Any] = None
    _embedding_model: Optional[Any] = None
    
    def add_triple(self, triple: SemanticTriple):
        """Add a triple to the graph."""
        self.triples.append(triple)
        self._nx_graph = None  # Invalidate cached graph
    
    def add_triples(self, triples: List[SemanticTriple]):
        """Add multiple triples."""
        self.triples.extend(triples)
        self._nx_graph = None
    
    def get_triples(self, subject: Optional[str] = None, 
                    predicate: Optional[TripleType] = None,
                    object: Optional[str] = None) -> List[SemanticTriple]:
        """Query triples by pattern."""
        results = []
        for t in self.triples:
            if subject and t.subject != subject:
                continue
            if predicate and t.predicate != predicate:
                continue
            if object and t.object != object:
                continue
            results.append(t)
        return results
    
    def get_neighbors(self, entity_id: str, 
                      predicate: Optional[TripleType] = None,
                      direction: str = "both") -> List[Tuple[TripleType, str]]:
        """Get neighboring entities."""
        neighbors = []
        for t in self.triples:
            if direction in ("both", "out") and t.subject == entity_id:
                if not predicate or t.predicate == predicate:
                    neighbors.append((t.predicate, t.object))
            if direction in ("both", "in") and t.object == entity_id:
                if not predicate or t.predicate == predicate:
                    neighbors.append((t.predicate, t.subject))
        return neighbors
    
    def to_networkx(self):
        """Convert to NetworkX graph for advanced algorithms."""
        if not NETWORKX_AVAILABLE:
            raise RuntimeError("NetworkX not available")
        
        if self._nx_graph is None:
            self._nx_graph = nx.MultiDiGraph()
            for t in self.triples:
                self._nx_graph.add_edge(t.subject, t.object, 
                                        predicate=t.predicate.value,
                                        confidence=t.confidence,
                                        source=t.source)
        return self._nx_graph
    
    def find_path(self, source: str, target: str, max_depth: int = 5) -> List[List[str]]:
        """Find paths between entities."""
        if not NETWORKX_AVAILABLE:
            return []
        
        G = self.to_networkx()
        try:
            paths = list(nx.all_simple_paths(G, source, target, cutoff=max_depth))
            return paths
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    
    def get_centrality(self) -> Dict[str, float]:
        """Compute PageRank centrality for entities."""
        if not NETWORKX_AVAILABLE:
            return {}
        
        G = self.to_networkx()
        try:
            return nx.pagerank(G)
        except Exception:
            return {}


class SemanticTripleExtractor:
    """Extracts semantic triples from project graph."""
    
    def __init__(self, project_graph: ProjectGraph):
        self.project_graph = project_graph
        self.triples: List[SemanticTriple] = []
    
    def extract_all(self) -> List[SemanticTriple]:
        """Extract all semantic triples from project graph."""
        self.triples = []
        
        self._extract_structural_triples()
        self._extract_architectural_triples()
        self._extract_business_triples()
        self._extract_evolution_triples()
        self._extract_semantic_similarity_triples()
        
        return self.triples
    
    def _extract_structural_triples(self):
        """Extract structural triples (file->class, class->method, etc.)."""
        # File -> Class
        for cls in self.project_graph.classes.values():
            file_entity = self.project_graph.files.get(cls.file_path)
            if file_entity:
                self.triples.append(SemanticTriple(
                    subject=f"file:{file_entity.relative_path}",
                    predicate=TripleType.CONTAINS,
                    object=f"class:{cls.qualified_name}",
                    source="structural_extractor"
                ))
        
        # File -> Function (module-level)
        for func in self.project_graph.functions.values():
            if not func.is_method:
                file_entity = self.project_graph.files.get(func.file_path)
                if file_entity:
                    self.triples.append(SemanticTriple(
                        subject=f"file:{file_entity.relative_path}",
                        predicate=TripleType.CONTAINS,
                        object=f"function:{func.qualified_name}",
                        source="structural_extractor"
                    ))
        
        # Class -> Method
        for cls in self.project_graph.classes.values():
            for method_name in cls.methods:
                # Find the method entity
                method_qualified = f"{cls.qualified_name}.{method_name}"
                if method_qualified in self.project_graph.functions:
                    self.triples.append(SemanticTriple(
                        subject=f"class:{cls.qualified_name}",
                        predicate=TripleType.DEFINES,
                        object=f"function:{method_qualified}",
                        source="structural_extractor"
                    ))
        
        # Inheritance
        for cls in self.project_graph.classes.values():
            for base in cls.base_classes:
                self.triples.append(SemanticTriple(
                    subject=f"class:{cls.qualified_name}",
                    predicate=TripleType.INHERITS,
                    object=f"class:{base}",
                    source="structural_extractor"
                ))
            
            for iface in cls.implemented_interfaces:
                self.triples.append(SemanticTriple(
                    subject=f"class:{cls.qualified_name}",
                    predicate=TripleType.IMPLEMENTS,
                    object=f"interface:{iface}",
                    source="structural_extractor"
                ))
        
        # Function calls
        for dep in self.project_graph.dependencies:
            if dep.dependency_type == "call":
                self.triples.append(SemanticTriple(
                    subject=f"function:{dep.source}",
                    predicate=TripleType.CALLS,
                    object=f"function:{dep.target}",
                    confidence=dep.strength,
                    source="structural_extractor"
                ))
        
        # Imports
        for dep in self.project_graph.dependencies:
            if dep.dependency_type == "import":
                self.triples.append(SemanticTriple(
                    subject=f"file:{dep.source}",
                    predicate=TripleType.IMPORTS,
                    object=f"module:{dep.target}",
                    source="structural_extractor"
                ))
    
    def _extract_architectural_triples(self):
        """Extract architectural layer triples."""
        # File -> Layer
        for file_entity in self.project_graph.files.values():
            if file_entity.architecture_layer != ArchitectureLayer.UNKNOWN:
                self.triples.append(SemanticTriple(
                    subject=f"file:{file_entity.relative_path}",
                    predicate=TripleType.BELONGS_TO_LAYER,
                    object=f"layer:{file_entity.architecture_layer.value}",
                    source="architectural_extractor"
                ))
        
        # Layer dependencies (from architecture analysis)
        for dep in self.project_graph.dependencies:
            if dep.dependency_type == "import":
                source_file = self.project_graph.files.get(dep.source)
                target_file = self.project_graph.files.get(dep.target)
                if source_file and target_file:
                    if (source_file.architecture_layer != ArchitectureLayer.UNKNOWN and
                        target_file.architecture_layer != ArchitectureLayer.UNKNOWN):
                        if source_file.architecture_layer != target_file.architecture_layer:
                            self.triples.append(SemanticTriple(
                                subject=f"layer:{source_file.architecture_layer.value}",
                                predicate=TripleType.DEPENDS_ON,
                                object=f"layer:{target_file.architecture_layer.value}",
                                confidence=dep.strength,
                                source="architectural_extractor"
                            ))
    
    def _extract_business_triples(self):
        """Extract business rule triples."""
        for rule in self.project_graph.business_rules:
            self.triples.append(SemanticTriple(
                subject=f"rule:{rule.id}",
                predicate=TripleType.ENFORCES,
                object=f"constraint:{rule.rule_type}",
                confidence=1.0 / rule.priority,
                source="business_extractor",
                metadata={"priority": rule.priority}
            ))
            
            for source_file in rule.source_files:
                self.triples.append(SemanticTriple(
                    subject=f"rule:{rule.id}",
                    predicate=TripleType.VALIDATES,
                    object=f"file:{source_file}",
                    source="business_extractor"
                ))
    
    def _extract_evolution_triples(self):
        """Extract evolution history triples."""
        for event in self.project_graph.evolution_events:
            for file_path in event.files_changed:
                self.triples.append(SemanticTriple(
                    subject=f"file:{file_path}",
                    predicate=TripleType.MODIFIED_IN,
                    object=f"commit:{event.commit_hash}",
                    source="evolution_extractor",
                    metadata={
                        "event_type": event.event_type,
                        "impact_score": event.impact_score
                    }
                ))
    
    def _extract_semantic_similarity_triples(self):
        """Extract semantic similarity triples (placeholder for vector-based)."""
        # This would use vector embeddings to find similar entities
        # Implemented in VectorEmbeddingManager
        pass


class VectorEmbeddingManager:
    """Manages vector embeddings for code entities."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self.embeddings: Dict[str, List[float]] = {}
        self._load_model()
    
    def _load_model(self):
        """Load sentence transformer model."""
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(self.model_name)
            except (Exception, OSError):
                self.model = None
    
    def embed_entity(self, entity_id: str, text: str) -> List[float]:
        """Generate embedding for an entity."""
        if self.model is None:
            # Return zero vector as fallback
            return [0.0] * 384  # Default dimension for MiniLM
        
        try:
            embedding = self.model.encode(text)
            self.embeddings[entity_id] = embedding.tolist()
            return embedding.tolist()
        except Exception:
            return [0.0] * 384
    
    def embed_class(self, cls: ClassEntity) -> List[float]:
        """Generate embedding for a class."""
        text = f"class {cls.name}"
        if cls.docstring:
            text += f" {cls.docstring}"
        if cls.methods:
            text += f" methods: {', '.join(cls.methods)}"
        if cls.base_classes:
            text += f" inherits: {', '.join(cls.base_classes)}"
        return self.embed_entity(f"class:{cls.qualified_name}", text)
    
    def embed_function(self, func: FunctionEntity) -> List[float]:
        """Generate embedding for a function."""
        text = f"function {func.name}"
        if func.docstring:
            text += f" {func.docstring}"
        if func.parameters:
            text += f" params: {', '.join(func.parameters)}"
        return self.embed_entity(f"function:{func.qualified_name}", text)
    
    def embed_file(self, file_entity: FileEntity) -> List[float]:
        """Generate embedding for a file."""
        # Use file path and architecture layer as context
        text = f"file {file_entity.relative_path} layer {file_entity.architecture_layer.value}"
        return self.embed_entity(f"file:{file_entity.relative_path}", text)
    
    def compute_similarity(self, entity_id1: str, entity_id2: str) -> float:
        """Compute cosine similarity between two entities."""
        emb1 = self.embeddings.get(entity_id1)
        emb2 = self.embeddings.get(entity_id2)
        
        if not emb1 or not emb2:
            return 0.0
        
        # Cosine similarity
        import math
        dot = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = math.sqrt(sum(a * a for a in emb1))
        norm2 = math.sqrt(sum(b * b for b in emb2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot / (norm1 * norm2)
    
    def find_similar(self, entity_id: str, top_k: int = 5, threshold: float = 0.7) -> List[Tuple[str, float]]:
        """Find similar entities."""
        if entity_id not in self.embeddings:
            return []
        
        similarities = []
        for other_id, emb in self.embeddings.items():
            if other_id != entity_id:
                sim = self.compute_similarity(entity_id, other_id)
                if sim >= threshold:
                    similarities.append((other_id, sim))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]


class CognitiveProjectModel:
    """Complete cognitive model combining knowledge graph and vector embeddings."""
    
    def __init__(self, project_graph: ProjectGraph):
        self.project_graph = project_graph
        self.knowledge_graph = KnowledgeGraph()
        self.embedding_manager = VectorEmbeddingManager()
        self._built = False
    
    def build(self):
        """Build the complete cognitive model."""
        # Extract semantic triples
        extractor = SemanticTripleExtractor(self.project_graph)
        triples = extractor.extract_all()
        self.knowledge_graph.add_triples(triples)
        
        # Generate vector embeddings
        self._generate_embeddings()
        
        # Add semantic similarity triples from embeddings
        self._add_similarity_triples()
        
        self._built = True
    
    def _generate_embeddings(self):
        """Generate embeddings for all entities."""
        # Classes
        for cls in self.project_graph.classes.values():
            self.embedding_manager.embed_class(cls)
        
        # Functions
        for func in self.project_graph.functions.values():
            self.embedding_manager.embed_function(func)
        
        # Files
        for file_entity in self.project_graph.files.values():
            self.embedding_manager.embed_file(file_entity)
    
    def _add_similarity_triples(self):
        """Add semantic similarity triples from embeddings."""
        entity_ids = list(self.embedding_manager.embeddings.keys())
        
        for entity_id in entity_ids:
            similar = self.embedding_manager.find_similar(entity_id, top_k=3, threshold=0.75)
            for similar_id, score in similar:
                self.knowledge_graph.add_triple(SemanticTriple(
                    subject=entity_id,
                    predicate=TripleType.SIMILAR_TO,
                    object=similar_id,
                    confidence=score,
                    source="vector_embedding"
                ))
    
    def query(self, query_text: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Semantic search by query text."""
        if self.embedding_manager.model is None:
            return []
        
        query_embedding = self.embedding_manager.model.encode(query_text)
        
        results = []
        for entity_id, emb in self.embedding_manager.embeddings.items():
            # Cosine similarity
            import math
            dot = sum(a * b for a, b in zip(query_embedding, emb))
            norm1 = math.sqrt(sum(a * a for a in query_embedding))
            norm2 = math.sqrt(sum(b * b for b in emb))
            
            if norm1 > 0 and norm2 > 0:
                sim = dot / (norm1 * norm2)
                if sim > 0.5:
                    results.append((entity_id, sim))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def get_context_for_task(self, task_description: str, max_entities: int = 20) -> Dict[str, Any]:
        """Get relevant context for a specific task."""
        # Semantic search
        relevant = self.query(task_description, top_k=max_entities)
        
        # Expand via graph traversal
        expanded = set()
        for entity_id, _ in relevant:
            expanded.add(entity_id)
            # Add neighbors
            for pred, neighbor in self.knowledge_graph.get_neighbors(entity_id):
                expanded.add(neighbor)
        
        # Build context
        context = {
            "entities": [],
            "triples": [],
            "summary": f"Found {len(relevant)} directly relevant entities, expanded to {len(expanded)}"
        }
        
        for entity_id in list(expanded)[:max_entities]:
            # Find entity details
            entity_info = self._get_entity_info(entity_id)
            if entity_info:
                context["entities"].append(entity_info)
            
            # Related triples
            for t in self.knowledge_graph.get_triples(subject=entity_id):
                context["triples"].append(t.to_dict())
        
        return context
    
    def _get_entity_info(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed info for an entity."""
        if entity_id.startswith("class:"):
            qualified = entity_id[6:]
            cls = self.project_graph.classes.get(qualified)
            if cls:
                return {
                    "id": entity_id,
                    "type": "class",
                    "name": cls.name,
                    "qualified_name": cls.qualified_name,
                    "file": cls.file_path,
                    "methods": cls.methods,
                    "base_classes": cls.base_classes,
                    "docstring": cls.docstring,
                }
        elif entity_id.startswith("function:"):
            qualified = entity_id[9:]
            func = self.project_graph.functions.get(qualified)
            if func:
                return {
                    "id": entity_id,
                    "type": "function",
                    "name": func.name,
                    "qualified_name": func.qualified_name,
                    "file": func.file_path,
                    "parameters": func.parameters,
                    "return_type": func.return_type,
                    "is_async": func.is_async,
                    "docstring": func.docstring,
                }
        elif entity_id.startswith("file:"):
            path = entity_id[5:]
            file_entity = self.project_graph.files.get(path)
            if file_entity:
                return {
                    "id": entity_id,
                    "type": "file",
                    "path": file_entity.relative_path,
                    "language": file_entity.language.value,
                    "lines": file_entity.lines_of_code,
                    "layer": file_entity.architecture_layer.value,
                }
        elif entity_id.startswith("rule:"):
            rule_id = entity_id[5:]
            for rule in self.project_graph.business_rules:
                if rule.id == rule_id:
                    return {
                        "id": entity_id,
                        "type": "business_rule",
                        "name": rule.name,
                        "description": rule.description,
                        "rule_type": rule.rule_type,
                        "priority": rule.priority,
                    }
        return None