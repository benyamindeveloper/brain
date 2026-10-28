"""Memory Layers (12.2) - Explicit separation of 5 memory layers in Knowledge Graph."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Set, List
from collections import defaultdict

from brain.models.core import ArchitectureLayer
from brain.cognitive.core import TripleType, SemanticTriple, KnowledgeGraph


class MemoryLayerType(str, Enum):
    """The 5 memory layers as defined in SDS 12.2."""
    PHYSICAL = "physical"           # files, folders, imports
    LOGICAL = "logical"             # classes, functions, interfaces
    ARCHITECTURAL = "architectural" # layers, modules, services
    BUSINESS = "business"           # rules, constraints, workflows
    EVOLUTION = "evolution"         # history, changes, decisions


@dataclass
class MemoryLayer:
    """A single memory layer with its entities and relationships."""
    layer_type: MemoryLayerType
    name: str
    description: str
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # entity_id -> metadata
    triples: List[SemanticTriple] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryLayerManager:
    """Manages the 5 memory layers with explicit separation."""
    
    LAYER_DEFINITIONS = {
        MemoryLayerType.PHYSICAL: {
            "name": "Physical Layer",
            "description": "Files, folders, imports - the physical code structure",
            "entity_prefixes": ["file:", "module:"],
            "predicates": [TripleType.CONTAINS, TripleType.IMPORTS],
        },
        MemoryLayerType.LOGICAL: {
            "name": "Logical Layer", 
            "description": "Classes, functions, interfaces - the logical code structure",
            "entity_prefixes": ["class:", "function:", "interface:"],
            "predicates": [TripleType.CONTAINS, TripleType.DEFINES, TripleType.INHERITS, 
                          TripleType.IMPLEMENTS, TripleType.CALLS],
        },
        MemoryLayerType.ARCHITECTURAL: {
            "name": "Architectural Layer",
            "description": "Layers, modules, services - the architectural structure",
            "entity_prefixes": ["layer:"],
            "predicates": [TripleType.BELONGS_TO_LAYER, TripleType.DEPENDS_ON, TripleType.VIOLATES],
        },
        MemoryLayerType.BUSINESS: {
            "name": "Business Layer",
            "description": "Rules, constraints, workflows - the business logic",
            "entity_prefixes": ["rule:", "constraint:", "workflow:"],
            "predicates": [TripleType.ENFORCES, TripleType.VALIDATES, TripleType.TRIGGERS],
        },
        MemoryLayerType.EVOLUTION: {
            "name": "Evolution Layer",
            "description": "History, changes, decisions - the evolutionary context",
            "entity_prefixes": ["commit:", "event:"],
            "predicates": [TripleType.MODIFIED_IN, TripleType.INTRODUCED_IN, TripleType.REFACTORED_IN],
        },
    }
    
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.knowledge_graph = knowledge_graph
        self.layers: Dict[MemoryLayerType, MemoryLayer] = {}
        self._initialize_layers()
    
    def _initialize_layers(self):
        """Initialize all 5 memory layers."""
        for layer_type, definition in self.LAYER_DEFINITIONS.items():
            self.layers[layer_type] = MemoryLayer(
                layer_type=layer_type,
                name=definition["name"],
                description=definition["description"],
            )
    
    def populate_from_knowledge_graph(self):
        """Populate layers from the knowledge graph triples."""
        # Clear existing layer data
        for layer in self.layers.values():
            layer.entities.clear()
            layer.triples.clear()
        
        # Distribute triples to appropriate layers
        for triple in self.knowledge_graph.triples:
            layer_type = self._classify_triple(triple)
            if layer_type:
                layer = self.layers[layer_type]
                layer.triples.append(triple)
                
                # Register entities in this layer
                for entity_id in [triple.subject, triple.object]:
                    if entity_id not in layer.entities:
                        layer.entities[entity_id] = {
                            "type": self._infer_entity_type(entity_id),
                            "first_seen_in_triple": triple.predicate.value,
                        }
        
        # Build layer metadata
        for layer_type, layer in self.layers.items():
            layer.metadata = {
                "entity_count": len(layer.entities),
                "triple_count": len(layer.triples),
                "entity_types": self._count_entity_types(layer),
                "predicate_types": self._count_predicate_types(layer),
            }
    
    def _classify_triple(self, triple: SemanticTriple) -> Optional[MemoryLayerType]:
        """Classify a triple into its memory layer."""
        for layer_type, definition in self.LAYER_DEFINITIONS.items():
            if triple.predicate in definition["predicates"]:
                return layer_type
        return None
    
    def _infer_entity_type(self, entity_id: str) -> str:
        """Infer entity type from its ID prefix."""
        if entity_id.startswith("file:"):
            return "file"
        elif entity_id.startswith("module:"):
            return "module"
        elif entity_id.startswith("class:"):
            return "class"
        elif entity_id.startswith("function:"):
            return "function"
        elif entity_id.startswith("interface:"):
            return "interface"
        elif entity_id.startswith("layer:"):
            return "layer"
        elif entity_id.startswith("rule:"):
            return "business_rule"
        elif entity_id.startswith("constraint:"):
            return "constraint"
        elif entity_id.startswith("workflow:"):
            return "workflow"
        elif entity_id.startswith("commit:"):
            return "commit"
        elif entity_id.startswith("event:"):
            return "event"
        return "unknown"
    
    def _count_entity_types(self, layer: MemoryLayer) -> Dict[str, int]:
        """Count entity types in a layer."""
        counts = defaultdict(int)
        for entity_info in layer.entities.values():
            counts[entity_info["type"]] += 1
        return dict(counts)
    
    def _count_predicate_types(self, layer: MemoryLayer) -> Dict[str, int]:
        """Count predicate types in a layer."""
        counts = defaultdict(int)
        for triple in layer.triples:
            counts[triple.predicate.value] += 1
        return dict(counts)
    
    def get_layer(self, layer_type: MemoryLayerType) -> Optional[MemoryLayer]:
        """Get a specific memory layer."""
        return self.layers.get(layer_type)
    
    def get_all_layers(self) -> Dict[MemoryLayerType, MemoryLayer]:
        """Get all memory layers."""
        return self.layers.copy()
    
    def get_layer_summary(self) -> Dict[str, Any]:
        """Get summary of all layers."""
        summary = {}
        for layer_type, layer in self.layers.items():
            summary[layer_type.value] = {
                "name": layer.name,
                "description": layer.description,
                "entity_count": len(layer.entities),
                "triple_count": len(layer.triples),
                "entity_types": layer.metadata.get("entity_types", {}),
                "predicate_types": layer.metadata.get("predicate_types", {}),
            }
        return summary
    
    def get_cross_layer_triples(self) -> List[SemanticTriple]:
        """Get triples that span multiple layers (cross-layer relationships)."""
        cross_layer = []
        for triple in self.knowledge_graph.triples:
            # Check if subject and object belong to different layers
            subj_layer = self._get_entity_layer(triple.subject)
            obj_layer = self._get_entity_layer(triple.object)
            if subj_layer and obj_layer and subj_layer != obj_layer:
                cross_layer.append(triple)
        return cross_layer
    
    def _get_entity_layer(self, entity_id: str) -> Optional[MemoryLayerType]:
        """Get the memory layer an entity belongs to."""
        for layer_type, definition in self.LAYER_DEFINITIONS.items():
            for prefix in definition["entity_prefixes"]:
                if entity_id.startswith(prefix):
                    return layer_type
        return None


class CrossLayerQueryEngine:
    """Query engine for cross-layer analysis."""
    
    def __init__(self, layer_manager: MemoryLayerManager):
        self.layer_manager = layer_manager
        self.kg = layer_manager.knowledge_graph
    
    def trace_physical_to_business(self, file_path: str) -> List[Dict[str, Any]]:
        """Trace from physical file to business rules it implements."""
        file_id = f"file:{file_path}"
        results = []
        
        # Get logical entities in this file
        logical_entities = self._get_entities_in_layer(file_id, MemoryLayerType.LOGICAL)
        
        for entity_id in logical_entities:
            # Find business rules that validate this entity
            rules = self._find_validating_rules(entity_id)
            for rule in rules:
                results.append({
                    "file": file_path,
                    "logical_entity": entity_id,
                    "business_rule": rule,
                    "trace": f"file -> {entity_id} -> {rule}"
                })
        
        return results
    
    def trace_business_to_evolution(self, rule_id: str) -> List[Dict[str, Any]]:
        """Trace from business rule to its evolution history."""
        rule_entity = f"rule:{rule_id}"
        results = []
        
        # Find files that implement this rule
        files = self._get_files_for_rule(rule_entity)
        
        for file_id in files:
            # Get evolution events for these files
            events = self._get_evolution_events(file_id)
            for event in events:
                results.append({
                    "business_rule": rule_id,
                    "file": file_id[5:],  # remove "file:" prefix
                    "event": event,
                    "trace": f"rule -> file -> commit"
                })
        
        return results
    
    def trace_architectural_impact(self, layer_name: str) -> List[Dict[str, Any]]:
        """Trace the impact of changing an architectural layer."""
        layer_entity = f"layer:{layer_name}"
        results = []
        
        # Get files in this layer
        files = self._get_entities_in_layer(layer_entity, MemoryLayerType.PHYSICAL)
        
        for file_id in files:
            # Get logical entities in this file
            logical = self._get_entities_in_layer(file_id, MemoryLayerType.LOGICAL)
            
            # Get business rules affected
            for entity_id in logical:
                rules = self._find_validating_rules(entity_id)
                for rule in rules:
                    results.append({
                        "layer": layer_name,
                        "file": file_id[5:],
                        "logical_entity": entity_id,
                        "business_rule": rule,
                    })
        
        return results
    
    def _get_entities_in_layer(self, source_id: str, target_layer: MemoryLayerType) -> List[str]:
        """Get entities in target layer connected to source."""
        definition = MemoryLayerManager.LAYER_DEFINITIONS[target_layer]
        results = []
        
        for triple in self.kg.triples:
            if triple.subject == source_id and triple.predicate in definition["predicates"]:
                results.append(triple.object)
            elif triple.object == source_id and triple.predicate in definition["predicates"]:
                results.append(triple.subject)
        
        return list(set(results))
    
    def _find_validating_rules(self, entity_id: str) -> List[str]:
        """Find business rules that validate an entity."""
        rules = []
        for triple in self.kg.triples:
            if triple.predicate == TripleType.VALIDATES and triple.subject.startswith("rule:") and triple.object == entity_id:
                rules.append(triple.subject)
        return rules
    
    def _get_files_for_rule(self, rule_id: str) -> List[str]:
        """Get files that implement a business rule."""
        files = []
        for triple in self.kg.triples:
            if triple.predicate == TripleType.VALIDATES and triple.subject == rule_id:
                # Find files containing this entity
                for t in self.kg.triples:
                    if t.predicate == TripleType.CONTAINS and t.object == triple.object and t.subject.startswith("file:"):
                        files.append(t.subject)
        return list(set(files))
    
    def _get_evolution_events(self, file_id: str) -> List[Dict[str, Any]]:
        """Get evolution events for a file."""
        events = []
        for triple in self.kg.triples:
            if triple.predicate == TripleType.MODIFIED_IN and triple.subject == file_id:
                events.append({
                    "commit": triple.object,
                    "event_type": triple.metadata.get("event_type"),
                    "impact_score": triple.metadata.get("impact_score"),
                })
        return events


def build_memory_layers(knowledge_graph: KnowledgeGraph) -> MemoryLayerManager:
    """Factory function to build memory layers from knowledge graph."""
    manager = MemoryLayerManager(knowledge_graph)
    manager.populate_from_knowledge_graph()
    return manager