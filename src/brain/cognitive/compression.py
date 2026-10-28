"""Context Compression Algorithm (13.3, RFC-02) - Token-aware prioritization for LLM context windows."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from collections import defaultdict
import math

from brain.cognitive.core import CognitiveProjectModel, KnowledgeGraph, SemanticTriple, TripleType
from brain.cognitive.query_interface import ComprehensiveQueryEngine
from brain.cognitive.memory_layers import MemoryLayerManager, MemoryLayerType
from brain.models.core import ProjectGraph, BusinessRuleEntity, EvolutionEventEntity


class CompressionStrategy(str, Enum):
    """Compression strategies for different scenarios."""
    AGGRESSIVE = "aggressive"        # Maximum compression, keep only critical
    BALANCED = "balanced"            # Balance between completeness and token limit
    CONSERVATIVE = "conservative"    # Minimal compression, keep most context
    TASK_AWARE = "task_aware"        # Adaptive based on task type


@dataclass
class CompressionConfig:
    """Configuration for context compression."""
    max_tokens: int = 8000
    strategy: CompressionStrategy = CompressionStrategy.TASK_AWARE
    preserve_business_rules: bool = True
    preserve_architecture: bool = True
    preserve_evolution: bool = True
    min_relevance_threshold: float = 0.3
    max_entities_per_layer: int = 50
    max_triples_per_layer: int = 200


@dataclass
class CompressedContext:
    """Result of context compression."""
    entities: List[Dict[str, Any]]
    triples: List[Dict[str, Any]]
    business_rules: List[Dict[str, Any]]
    evolution_events: List[Dict[str, Any]]
    layer_summaries: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    estimated_tokens: int = 0
    compression_ratio: float = 1.0


class TokenEstimator:
    """Estimate token count for context elements."""
    
    # Rough token estimates (1 token ≈ 4 chars for English, ~3 for code)
    CHAR_PER_TOKEN = 3.5
    
    @classmethod
    def estimate_string(cls, text: str) -> int:
        """Estimate tokens for a string."""
        return max(1, int(len(text) / cls.CHAR_PER_TOKEN))
    
    @classmethod
    def estimate_entity(cls, entity: Dict[str, Any]) -> int:
        """Estimate tokens for an entity."""
        # Base tokens for entity structure
        base = 50
        # Add tokens for each field
        for key, value in entity.items():
            if isinstance(value, str):
                base += cls.estimate_string(value)
            elif isinstance(value, list):
                base += sum(cls.estimate_string(str(v)) for v in value)
            elif isinstance(value, dict):
                base += cls.estimate_string(str(value))
        return base
    
    @classmethod
    def estimate_triple(cls, triple: Dict[str, Any]) -> int:
        """Estimate tokens for a triple."""
        return cls.estimate_string(f"{triple.get('subject', '')} {triple.get('predicate', '')} {triple.get('object', '')}")
    
    @classmethod
    def estimate_context(cls, context: Dict[str, Any]) -> int:
        """Estimate total tokens for a context dictionary."""
        total = 0
        for key, value in context.items():
            if isinstance(value, list):
                if key == "entities":
                    total += sum(cls.estimate_entity(e) for e in value)
                elif key == "triples":
                    total += sum(cls.estimate_triple(t) for t in value)
                elif key == "business_rules":
                    total += sum(cls.estimate_entity(r) for r in value)
                elif key == "evolution_events":
                    total += sum(cls.estimate_entity(e) for e in value)
                else:
                    total += cls.estimate_string(str(value))
            elif isinstance(value, dict):
                total += cls.estimate_string(str(value))
            else:
                total += cls.estimate_string(str(value))
        return total


class RelevanceScorer:
    """Score relevance of entities/triples for a given task."""
    
    def __init__(self, query_engine: ComprehensiveQueryEngine = None):
        self.query_engine = query_engine
    
    def score_entity(self, entity: Dict[str, Any], task_description: str, 
                     task_type: str = "") -> float:
        """Score entity relevance for a task."""
        score = 0.0
        
        # Base score from direct relevance
        if "id" in entity:
            entity_id = entity["id"]
            # Check if entity ID contains task keywords
            task_keywords = task_description.lower().split()
            entity_text = entity_id.lower()
            for kw in task_keywords:
                if len(kw) > 3 and kw in entity_text:
                    score += 0.3
        
        # Boost for entity type relevance
        entity_type = entity.get("type", "")
        type_boost = {
            "class": 0.2,
            "function": 0.2,
            "business_rule": 0.4,
            "file": 0.1,
            "layer": 0.3,
        }
        score += type_boost.get(entity_type, 0.0)
        
        # Boost for direct task type match
        if task_type:
            if task_type == "refactoring" and entity_type in ["class", "function"]:
                score += 0.2
            elif task_type == "bug_fix" and entity_type in ["function", "business_rule"]:
                score += 0.3
            elif task_type == "code_generation" and entity_type in ["class", "function", "layer"]:
                score += 0.2
        
        return min(score, 1.0)
    
    def score_triple(self, triple: Dict[str, Any], task_description: str) -> float:
        """Score triple relevance for a task."""
        score = 0.0
        
        # Predicate relevance
        predicate = triple.get("predicate", "")
        predicate_weights = {
            "enforces": 0.4,
            "validates": 0.3,
            "depends_on": 0.3,
            "contains": 0.2,
            "defines": 0.2,
            "calls": 0.2,
            "inherits": 0.15,
            "imports": 0.1,
            "modified_in": 0.25,
            "similar_to": 0.15,
        }
        score += predicate_weights.get(predicate, 0.1)
        
        # Entity relevance
        for entity_id in [triple.get("subject", ""), triple.get("object", "")]:
            if any(kw in entity_id.lower() for kw in task_description.lower().split() if len(kw) > 3):
                score += 0.2
        
        return min(score, 1.0)


class ContextCompressor:
    """Main context compression engine (RFC-02)."""
    
    def __init__(self, config: CompressionConfig = None):
        self.config = config or CompressionConfig()
        self.token_estimator = TokenEstimator()
        self.relevance_scorer = RelevanceScorer()
    
    def compress(self, cognitive_model: CognitiveProjectModel, 
                 task_description: str,
                 task_type: str = "",
                 query_engine: ComprehensiveQueryEngine = None) -> CompressedContext:
        """Compress cognitive context for a specific task."""
        
        # Update relevance scorer with query engine
        self.relevance_scorer.query_engine = query_engine
        
        # Get full context from cognitive model
        full_context = cognitive_model.get_context_for_task(task_description, max_entities=200)
        
        # Score and filter entities
        entities = full_context.get("entities", [])
        scored_entities = [
            (e, self.relevance_scorer.score_entity(e, task_description, full_context.get("task_type", "")))
            for e in entities
        ]
        scored_entities.sort(key=lambda x: x[1], reverse=True)
        
        # Score triples
        triples = full_context.get("triples", [])
        scored_triples = [
            (t, self.relevance_scorer.score_triple(t, task_description))
            for t in triples
        ]
        scored_triples.sort(key=lambda x: x[1], reverse=True)
        
        # Apply compression strategy
        if self.config.strategy == CompressionStrategy.TASK_AWARE:
            return self._compress_task_aware(scored_entities, scored_triples, full_context, task_description)
        elif self.config.strategy == CompressionStrategy.AGGRESSIVE:
            return self._compress_aggressive(scored_entities, scored_triples, full_context)
        elif self.config.strategy == CompressionStrategy.BALANCED:
            return self._compress_balanced(scored_entities, scored_triples, full_context)
        else:  # CONSERVATIVE
            return self._compress_conservative(scored_entities, scored_triples, full_context)
    
    def _compress_task_aware(self, scored_entities, scored_triples, full_context, task_description) -> CompressedContext:
        """Task-aware compression strategy."""
        # Select entities by layer and relevance
        selected_entities = self._select_entities_by_layer(scored_entities)
        
        # Select triples connecting selected entities
        selected_entity_ids = {e["id"] for e in selected_entities}
        selected_triples = self._select_connected_triples(scored_triples, selected_entity_ids)
        
        # Always include high-priority business rules
        business_rules = self._select_business_rules(full_context.get("business_rules", []))
        
        # Include recent evolution events
        evolution_events = self._select_evolution_events(full_context.get("evolution_events", []))
        
        # Build layer summaries
        layer_summaries = self._build_layer_summaries(selected_entities, scored_triples)
        
        context = CompressedContext(
            entities=selected_entities,
            triples=selected_triples,
            business_rules=business_rules,
            evolution_events=evolution_events,
            layer_summaries=layer_summaries,
            metadata={
                "task_description": task_description[:200],
                "total_entities_available": len(scored_entities),
                "total_triples_available": len(scored_triples),
            },
        )
        
        # Estimate tokens
        context.estimated_tokens = self.token_estimator.estimate_context({
            "entities": context.entities,
            "triples": context.triples,
            "business_rules": context.business_rules,
            "evolution_events": context.evolution_events,
            "layer_summaries": context.layer_summaries,
        })
        
        # Calculate compression ratio
        original_tokens = self._estimate_original_tokens(full_context)
        context.compression_ratio = context.estimated_tokens / original_tokens if original_tokens > 0 else 1.0
        
        # Ensure within token limit
        if context.estimated_tokens > self.config.max_tokens:
            context = self._trim_to_token_limit(context)
        
        return context
    
    def _select_entities_by_layer(self, scored_entities) -> List[Dict[str, Any]]:
        """Select top entities from each layer."""
        layer_entities = defaultdict(list)
        
        for entity, score in scored_entities:
            if score < self.config.min_relevance_threshold:
                continue
            entity_id = entity.get("id", "")
            layer = self._get_entity_layer(entity_id)
            layer_entities[layer].append((entity, score))
        
        selected = []
        for layer, entities in layer_entities.items():
            # Sort by score and take top N per layer
            entities.sort(key=lambda x: x[1], reverse=True)
            max_per_layer = min(self.config.max_entities_per_layer, len(entities))
            selected.extend([e for e, _ in entities[:max_per_layer]])
        
        return selected
    
    def _select_connected_triples(self, scored_triples, entity_ids: Set[str]) -> List[Dict[str, Any]]:
        """Select triples that connect selected entities."""
        selected = []
        connected = set()
        
        for triple, score in scored_triples:
            if score < self.config.min_relevance_threshold:
                continue
            
            subj = triple.get("subject", "")
            obj = triple.get("object", "")
            
            # Include if both entities are selected
            if subj in entity_ids and obj in entity_ids:
                selected.append(triple)
                connected.add(subj)
                connected.add(obj)
            # Include if one entity is selected and triple is high relevance
            elif (subj in entity_ids or obj in entity_ids) and score > 0.5:
                selected.append(triple)
                connected.add(subj)
                connected.add(obj)
        
        # Sort by score and limit
        selected.sort(key=lambda t: self.relevance_scorer.score_triple(t, ""), reverse=True)
        return selected[:self.config.max_triples_per_layer]
    
    def _select_business_rules(self, all_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select high-priority business rules."""
        if not self.config.preserve_business_rules:
            return []
        
        # Sort by priority (lower = higher priority)
        sorted_rules = sorted(all_rules, key=lambda r: r.get("priority", 999))
        return sorted_rules[:20]  # Max 20 business rules
    
    def _select_evolution_events(self, all_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select recent high-impact evolution events."""
        if not self.config.preserve_evolution:
            return []
        
        # Sort by timestamp descending, then by impact score
        sorted_events = sorted(
            all_events, 
            key=lambda e: (e.get("timestamp", 0), e.get("impact_score", 0)), 
            reverse=True
        )
        return sorted_events[:10]
    
    def _build_layer_summaries(self, entities, triples) -> Dict[str, Any]:
        """Build summaries for each memory layer."""
        layer_entities = defaultdict(list)
        layer_triples = defaultdict(list)
        
        for entity in entities:
            layer = self._get_entity_layer(entity.get("id", ""))
            layer_entities[layer].append(entity)
        
        for triple in triples:
            layer = self._get_triple_layer(triple)
            layer_triples[layer].append(triple)
        
        summaries = {}
        for layer in MemoryLayerType:
            summaries[layer.value] = {
                "entity_count": len(layer_entities.get(layer, [])),
                "triple_count": len(layer_triples.get(layer, [])),
                "key_entities": [e.get("id", "") for e in layer_entities.get(layer, [])[:5]],
            }
        
        return summaries
    
    def _get_entity_layer(self, entity_id: str) -> MemoryLayerType:
        """Get memory layer for entity ID."""
        if entity_id.startswith("file:") or entity_id.startswith("module:"):
            return MemoryLayerType.PHYSICAL
        elif entity_id.startswith("class:") or entity_id.startswith("function:") or entity_id.startswith("interface:"):
            return MemoryLayerType.LOGICAL
        elif entity_id.startswith("layer:"):
            return MemoryLayerType.ARCHITECTURAL
        elif entity_id.startswith("rule:") or entity_id.startswith("constraint:") or entity_id.startswith("workflow:"):
            return MemoryLayerType.BUSINESS
        elif entity_id.startswith("commit:") or entity_id.startswith("event:"):
            return MemoryLayerType.EVOLUTION
        return MemoryLayerType.PHYSICAL
    
    def _get_triple_layer(self, triple: Dict[str, Any]) -> MemoryLayerType:
        """Get memory layer for a triple based on predicate."""
        predicate = triple.get("predicate", "")
        if predicate in ["CONTAINS", "IMPORTS"]:
            return MemoryLayerType.PHYSICAL
        elif predicate in ["DEFINES", "INHERITS", "IMPLEMENTS", "CALLS"]:
            return MemoryLayerType.LOGICAL
        elif predicate in ["BELONGS_TO_LAYER", "DEPENDS_ON", "VIOLATES"]:
            return MemoryLayerType.ARCHITECTURAL
        elif predicate in ["ENFORCES", "VALIDATES", "TRIGGERS"]:
            return MemoryLayerType.BUSINESS
        elif predicate in ["MODIFIED_IN", "INTRODUCED_IN", "REFACTORED_IN"]:
            return MemoryLayerType.EVOLUTION
        return MemoryLayerType.PHYSICAL
    
    def _trim_to_token_limit(self, context: CompressedContext) -> CompressedContext:
        """Trim context to fit within token limit."""
        # Reduce entities first
        while context.estimated_tokens > self.config.max_tokens and context.entities:
            context.entities.pop()
            context.estimated_tokens = self.token_estimator.estimate_context({
                "entities": context.entities,
                "triples": context.triples,
                "business_rules": context.business_rules,
                "evolution_events": context.evolution_events,
                "layer_summaries": context.layer_summaries,
            })
        
        # Then reduce triples
        while context.estimated_tokens > self.config.max_tokens and context.triples:
            context.triples.pop()
            context.estimated_tokens = self.token_estimator.estimate_context({
                "entities": context.entities,
                "triples": context.triples,
                "business_rules": context.business_rules,
                "evolution_events": context.evolution_events,
                "layer_summaries": context.layer_summaries,
            })
        
        return context
    
    def _compress_aggressive(self, scored_entities, scored_triples, full_context) -> CompressedContext:
        """Aggressive compression - keep only top 10%."""
        # Take top 10% of entities and triples
        n_entities = max(1, len(scored_entities) // 10)
        n_triples = max(1, len(scored_triples) // 10)
        
        return CompressedContext(
            entities=[e for e, _ in scored_entities[:n_entities]],
            triples=[t for t, _ in scored_triples[:n_triples]],
            business_rules=[],
            evolution_events=[],
            layer_summaries={},
        )
    
    def _compress_balanced(self, scored_entities, scored_triples, full_context) -> CompressedContext:
        """Balanced compression - keep top 30%."""
        n_entities = max(5, len(scored_entities) * 3 // 10)
        n_triples = max(10, len(scored_triples) * 3 // 10)
        
        return CompressedContext(
            entities=[e for e, _ in scored_entities[:n_entities]],
            triples=[t for t, _ in scored_triples[:n_triples]],
            business_rules=full_context.get("business_rules", [])[:10],
            evolution_events=full_context.get("evolution_events", [])[:5],
            layer_summaries={},
        )
    
    def _compress_conservative(self, scored_entities, scored_triples, full_context) -> CompressedContext:
        """Conservative compression - keep top 70%."""
        n_entities = max(10, len(scored_entities) * 7 // 10)
        n_triples = max(20, len(scored_triples) * 7 // 10)
        
        return CompressedContext(
            entities=[e for e, _ in scored_entities[:n_entities]],
            triples=[t for t, _ in scored_triples[:n_triples]],
            business_rules=full_context.get("business_rules", [])[:20],
            evolution_events=full_context.get("evolution_events", [])[:10],
            layer_summaries={},
        )
    
    def _estimate_original_tokens(self, full_context: Dict[str, Any]) -> int:
        """Estimate tokens in original context."""
        return self.token_estimator.estimate_context(full_context)


def create_compressor(config: CompressionConfig = None) -> ContextCompressor:
    """Factory function to create context compressor."""
    return ContextCompressor(config)