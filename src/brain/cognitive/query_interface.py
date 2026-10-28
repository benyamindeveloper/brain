"""Query Interface (12.3) - Graph traversal, semantic search, path finding, centrality analysis."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple, Iterator
from enum import Enum
from collections import defaultdict, deque
import heapq

from brain.cognitive.core import TripleType, SemanticTriple, KnowledgeGraph, TripleType
from brain.cognitive.memory_layers import MemoryLayerManager, MemoryLayerType, CrossLayerQueryEngine


class QueryType(str, Enum):
    """Types of queries supported by the interface."""
    SEMANTIC_SEARCH = "semantic_search"
    GRAPH_TRAVERSAL = "graph_traversal"
    PATH_FINDING = "path_finding"
    CENTRALITY = "centrality"
    SUBGRAPH = "subgraph"
    PATTERN_MATCH = "pattern_match"
    CROSS_LAYER = "cross_layer"


@dataclass
class QueryResult:
    """Result of a query execution."""
    query_type: QueryType
    results: List[Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0


class GraphQueryEngine:
    """Advanced graph query engine for the knowledge graph."""
    
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self._nx_graph = None
    
    def _ensure_networkx(self):
        """Ensure NetworkX graph is built."""
        if self._nx_graph is None:
            self._nx_graph = self.kg.to_networkx()
        return self._nx_graph
    
    def bfs_traversal(self, start: str, max_depth: int = 3, 
                      predicate_filter: Optional[List[TripleType]] = None) -> List[Dict[str, Any]]:
        """Breadth-first traversal from a starting entity."""
        visited = set()
        queue = deque([(start, 0, [])])
        results = []
        
        while queue:
            current, depth, path = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            
            results.append({
                "entity": current,
                "depth": depth,
                "path": path,
            })
            
            neighbors = self.kg.get_neighbors(current)
            for pred, neighbor in neighbors:
                if predicate_filter and pred not in predicate_filter:
                    continue
                queue.append((neighbor, depth + 1, path + [(pred.value, current)]))
        
        return results
    
    def dfs_traversal(self, start: str, max_depth: int = 3,
                      predicate_filter: Optional[List[TripleType]] = None) -> List[Dict[str, Any]]:
        """Depth-first traversal from a starting entity."""
        visited = set()
        results = []
        
        def dfs(current: str, depth: int, path: List[Tuple[str, str]]):
            if current in visited or depth > max_depth:
                return
            visited.add(current)
            results.append({
                "entity": current,
                "depth": depth,
                "path": path,
            })
            
            neighbors = self.kg.get_neighbors(current)
            for pred, neighbor in neighbors:
                if predicate_filter and pred not in predicate_filter:
                    continue
                dfs(neighbor, depth + 1, path + [(pred.value, current)])
        
        dfs(start, 0, [])
        return results
    
    def find_shortest_path(self, source: str, target: str, 
                           max_depth: int = 10) -> Optional[List[Dict[str, Any]]]:
        """Find shortest path between two entities using BFS."""
        if not self.kg._nx_graph:
            try:
                self._ensure_networkx()
            except Exception:
                return None
        
        G = self._nx_graph
        try:
            path = nx.shortest_path(G, source, target)
            # Build detailed path info
            detailed = []
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                # Find the predicate
                edge_data = G.get_edge_data(u, v)
                pred = list(edge_data.values())[0].get('predicate', 'related') if edge_data else 'related'
                detailed.append({
                    "from": u,
                    "to": v,
                    "predicate": pred,
                })
            return detailed
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
    
    def find_all_paths(self, source: str, target: str, 
                       max_depth: int = 5, max_paths: int = 10) -> List[List[Dict[str, Any]]]:
        """Find all paths between two entities up to max_depth."""
        G = self._ensure_networkx()
        paths = []
        
        try:
            for path in nx.all_simple_paths(G, source, target, cutoff=max_depth):
                detailed = []
                for i in range(len(path) - 1):
                    u, v = path[i], path[i + 1]
                    edge_data = G.get_edge_data(u, v)
                    pred = list(edge_data.values())[0].get('predicate', 'related') if edge_data else 'related'
                    detailed.append({
                        "from": u,
                        "to": v,
                        "predicate": pred,
                    })
                paths.append(detailed)
                if len(paths) >= max_paths:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass
        
        return paths
    
    def compute_centrality(self, method: str = "pagerank") -> Dict[str, float]:
        """Compute various centrality measures."""
        G = self._ensure_networkx()
        
        try:
            if method == "pagerank":
                return nx.pagerank(G)
            elif method == "betweenness":
                return nx.betweenness_centrality(G)
            elif method == "closeness":
                return nx.closeness_centrality(G)
            elif method == "degree":
                return dict(G.degree())
            elif method == "eigenvector":
                return nx.eigenvector_centrality(G, max_iter=1000)
        except Exception:
            return {}
        return {}
    
    def get_subgraph(self, entities: List[str], include_neighbors: bool = True, 
                     neighbor_depth: int = 1) -> KnowledgeGraph:
        """Extract a subgraph for the given entities."""
        entity_set = set(entities)
        
        if include_neighbors:
            for entity in entities:
                neighbors = self.kg.get_neighbors(entity)
                for _, neighbor in neighbors:
                    entity_set.add(neighbor)
        
        # Filter triples
        filtered_triples = [
            t for t in self.kg.triples
            if t.subject in entity_set and t.object in entity_set
        ]
        
        subgraph = KnowledgeGraph()
        subgraph.add_triples(filtered_triples)
        return subgraph
    
    def find_clusters(self, min_cluster_size: int = 3) -> List[List[str]]:
        """Find connected components (clusters) in the graph."""
        G = self._ensure_networkx()
        
        try:
            clusters = list(nx.weakly_connected_components(G))
            return [list(c) for c in clusters if len(c) >= min_cluster_size]
        except Exception:
            return []
    
    def find_cycles(self, max_length: int = 6) -> List[List[str]]:
        """Find cycles in the graph."""
        G = self._ensure_networkx()
        cycles = []
        
        try:
            for cycle in nx.simple_cycles(G):
                if len(cycle) <= max_length:
                    cycles.append(cycle)
        except Exception:
            pass
        
        return cycles
    
    def get_influence_score(self, entity_id: str) -> float:
        """Calculate influence score for an entity based on centrality and connections."""
        centrality = self.compute_centrality("pagerank")
        base_score = centrality.get(entity_id, 0.0)
        
        # Add connection-based score
        neighbors = self.kg.get_neighbors(entity_id)
        connection_bonus = len(neighbors) * 0.01
        
        return base_score + connection_bonus


class SemanticSearchEngine:
    """Semantic search engine using vector embeddings."""
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
    
    def search(self, query: str, top_k: int = 10, 
               entity_type_filter: Optional[str] = None,
               min_similarity: float = 0.5) -> List[Dict[str, Any]]:
        """Search for entities similar to query text."""
        if self.embedding_manager.model is None:
            return []
        
        query_embedding = self.embedding_manager.model.encode(query)
        
        results = []
        for entity_id, emb in self.embedding_manager.embeddings.items():
            if entity_type_filter and not entity_id.startswith(entity_type_filter):
                continue
            
            import math
            dot = sum(a * b for a, b in zip(query_embedding, emb))
            norm1 = math.sqrt(sum(a * a for a in query_embedding))
            norm2 = math.sqrt(sum(b * b for b in emb))
            
            if norm1 > 0 and norm2 > 0:
                sim = dot / (norm1 * norm2)
                if sim >= min_similarity:
                    results.append({
                        "entity_id": entity_id,
                        "similarity": sim,
                        "entity_type": self._get_entity_type(entity_id),
                    })
        
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
    
    def _get_entity_type(self, entity_id: str) -> str:
        """Get entity type from ID prefix."""
        if entity_id.startswith("file:"):
            return "file"
        elif entity_id.startswith("class:"):
            return "class"
        elif entity_id.startswith("function:"):
            return "function"
        elif entity_id.startswith("layer:"):
            return "layer"
        elif entity_id.startswith("rule:"):
            return "business_rule"
        return "unknown"


class PatternMatcher:
    """Pattern matching for common code patterns in the knowledge graph."""
    
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
    
    def find_factory_patterns(self) -> List[Dict[str, Any]]:
        """Find factory pattern implementations."""
        patterns = []
        for triple in self.kg.triples:
            if (triple.predicate == TripleType.DEFINES and 
                "factory" in triple.object.lower()):
                # Get the class that defines this factory
                for t in self.kg.triples:
                    if t.predicate == TripleType.CONTAINS and t.object == triple.subject:
                        patterns.append({
                            "factory_class": t.subject[5:],  # remove "file:"
                            "factory_method": triple.object[9:],  # remove "function:"
                        })
        return patterns
    
    def find_singleton_patterns(self) -> List[Dict[str, Any]]:
        """Find singleton pattern implementations."""
        patterns = []
        for triple in self.kg.triples:
            if (triple.predicate == TripleType.DEFINES and 
                ("singleton" in triple.object.lower() or 
                 "getinstance" in triple.object.lower())):
                for t in self.kg.triples:
                    if t.predicate == TripleType.CONTAINS and t.object == triple.subject:
                        patterns.append({
                            "singleton_class": t.subject[5:],
                            "method": triple.object[9:],
                        })
        return patterns
    
    def find_observer_patterns(self) -> List[Dict[str, Any]]:
        """Find observer pattern implementations."""
        patterns = []
        for triple in self.kg.triples:
            if (triple.predicate == TripleType.DEFINES and 
                ("observer" in triple.object.lower() or 
                 "subscribe" in triple.object.lower() or
                 "notify" in triple.object.lower())):
                for t in self.kg.triples:
                    if t.predicate == TripleType.CONTAINS and t.object == triple.subject:
                        patterns.append({
                            "observer_class": t.subject[5:],
                            "method": triple.object[9:],
                        })
        return patterns
    
    def find_repository_patterns(self) -> List[Dict[str, Any]]:
        """Find repository pattern implementations."""
        patterns = []
        for triple in self.kg.triples:
            if (triple.predicate in [TripleType.DEFINES, TripleType.IMPLEMENTS] and
                "repository" in triple.object.lower()):
                for t in self.kg.triples:
                    if t.predicate == TripleType.CONTAINS and t.object == triple.subject:
                        patterns.append({
                            "repository_class": t.subject[5:],
                            "interface": triple.object,
                        })
        return patterns


class ComprehensiveQueryEngine:
    """Unified query engine combining all query types."""
    
    def __init__(self, knowledge_graph: KnowledgeGraph, embedding_manager, layer_manager):
        self.graph_engine = GraphQueryEngine(knowledge_graph)
        self.semantic_engine = SemanticSearchEngine(embedding_manager)
        self.pattern_matcher = PatternMatcher(knowledge_graph)
        self.cross_layer_engine = CrossLayerQueryEngine(layer_manager)
        self.layer_manager = layer_manager
    
    def execute_query(self, query_type: QueryType, params: Dict[str, Any]) -> QueryResult:
        """Execute a query of the specified type."""
        import time
        start = time.time()
        
        try:
            if query_type == QueryType.SEMANTIC_SEARCH:
                results = self.semantic_engine.search(**params)
            elif query_type == QueryType.GRAPH_TRAVERSAL:
                results = self.graph_engine.bfs_traversal(**params)
            elif query_type == QueryType.PATH_FINDING:
                results = self.graph_engine.find_all_paths(**params)
            elif query_type == QueryType.CENTRALITY:
                results = self.graph_engine.compute_centrality(**params)
            elif query_type == QueryType.SUBGRAPH:
                subgraph = self.graph_engine.get_subgraph(**params)
                results = {"entities": len(subgraph.triples), "triples": len(subgraph.triples)}
            elif query_type == QueryType.PATTERN_MATCH:
                pattern = params.get("pattern", "all")
                if pattern == "factory":
                    results = self.pattern_matcher.find_factory_patterns()
                elif pattern == "singleton":
                    results = self.pattern_matcher.find_singleton_patterns()
                elif pattern == "observer":
                    results = self.pattern_matcher.find_observer_patterns()
                elif pattern == "repository":
                    results = self.pattern_matcher.find_repository_patterns()
                else:
                    results = {
                        "factory": self.pattern_matcher.find_factory_patterns(),
                        "singleton": self.pattern_matcher.find_singleton_patterns(),
                        "observer": self.pattern_matcher.find_observer_patterns(),
                        "repository": self.pattern_matcher.find_repository_patterns(),
                    }
            elif query_type == QueryType.CROSS_LAYER:
                query = params.get("query", "physical_to_business")
                if query == "physical_to_business":
                    results = self.cross_layer_engine.trace_physical_to_business(**params)
                elif query == "business_to_evolution":
                    results = self.cross_layer_engine.trace_business_to_evolution(**params)
                elif query == "architectural_impact":
                    results = self.cross_layer_engine.trace_architectural_impact(**params)
            else:
                results = {"error": f"Unknown query type: {query_type}"}
            
            return QueryResult(
                query_type=query_type,
                results=results,
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return QueryResult(
                query_type=query_type,
                results=[],
                metadata={"error": str(e)},
                execution_time_ms=(time.time() - start) * 1000,
            )
    
    def get_layer_summary(self) -> Dict[str, Any]:
        """Get summary of all memory layers."""
        return self.layer_manager.get_layer_summary()
    
    def get_cross_layer_analysis(self) -> Dict[str, Any]:
        """Get cross-layer relationship analysis."""
        cross_triples = self.layer_manager.get_cross_layer_triples()
        return {
            "cross_layer_count": len(cross_triples),
            "relationships": [
                {
                    "subject": t.subject,
                    "predicate": t.predicate.value,
                    "object": t.object,
                }
                for t in cross_triples[:50]
            ],
        }


def create_query_engine(knowledge_graph: KnowledgeGraph, embedding_manager, 
                       layer_manager: MemoryLayerManager) -> ComprehensiveQueryEngine:
    """Factory function to create the comprehensive query engine."""
    return ComprehensiveQueryEngine(knowledge_graph, embedding_manager, layer_manager)