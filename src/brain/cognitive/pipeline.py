"""AI Pipeline (13.1) - 10-stage pipeline from user input to learning feedback."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from pathlib import Path
import uuid

from brain.cognitive.core import CognitiveProjectModel
from brain.cognitive.prompt_engine import PromptEngine, GeneratedPrompt, TaskType
from brain.cognitive.query_interface import ComprehensiveQueryEngine, QueryType, QueryResult
from brain.cognitive.memory_layers import MemoryLayerManager, CrossLayerQueryEngine
from brain.guard.engine import GuardEngine, GuardResult, RiskLevel
from brain.storage.sqlite_storage import SQLiteStorage
from brain.llm.client import LLMClientFactory, BaseLLMClient
from brain.llm.config import LLMConfig, LLMProvider
from brain.models.core import ProjectGraph


class PipelineStage(str, Enum):
    """The 10 pipeline stages as defined in SDS 13.1."""
    STAGE_1_INPUT_PARSING = "input_parsing"           # Parse and understand user input
    STAGE_2_CONTEXT_RETRIEVAL = "context_retrieval"   # Retrieve relevant context from cognitive model
    STAGE_3_TASK_CLASSIFICATION = "task_classification"  # Classify task type
    STAGE_4_PROMPT_CONSTRUCTION = "prompt_construction"  # Build optimal prompt
    STAGE_5_PRE_VALIDATION = "pre_validation"         # Pre-execution validation
    STAGE_6_LLM_EXECUTION = "llm_execution"           # Execute with LLM
    STAGE_7_POST_VALIDATION = "post_validation"       # Post-execution validation
    STAGE_8_RISK_ASSESSMENT = "risk_assessment"       # Risk scoring
    STAGE_9_EXECUTION = "execution"                   # Apply changes
    STAGE_10_LEARNING = "learning"                    # Learn from outcome


@dataclass
class PipelineContext:
    """Context passed through pipeline stages."""
    user_input: str
    project_root: Path
    project_graph: Optional[ProjectGraph] = None
    cognitive_model: Optional[CognitiveProjectModel] = None
    query_engine: Optional[ComprehensiveQueryEngine] = None
    guard_engine: Optional[GuardEngine] = None
    prompt_engine: Optional[PromptEngine] = None
    llm_client: Optional[BaseLLMClient] = None
    llm_config: Optional[LLMConfig] = None
    
    # Stage outputs
    parsed_intent: Optional[Dict[str, Any]] = None
    retrieved_context: Optional[Dict[str, Any]] = None
    task_type: Optional[TaskType] = None
    generated_prompt: Optional[GeneratedPrompt] = None
    pre_validation: Optional[Any] = None
    llm_response: Optional[str] = None
    post_validation: Optional[Any] = None
    risk_assessment: Optional[Any] = None
    execution_result: Optional[Dict[str, Any]] = None
    learning_feedback: Optional[Dict[str, Any]] = None
    
    # Metadata
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: datetime = field(default_factory=datetime.now)
    current_stage: Optional[PipelineStage] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineStageResult:
    """Result of a single pipeline stage."""
    stage: PipelineStage
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineStageBase:
    """Base class for pipeline stages."""
    
    def __init__(self, name: PipelineStage):
        self.name = name
    
    def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Execute the stage."""
        import time
        start = time.time()
        try:
            output = self.run(context)
            return PipelineStageResult(
                stage=self.name,
                success=True,
                output=output,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return PipelineStageResult(
                stage=self.name,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )
    
    def run(self, context: PipelineContext) -> Any:
        """Override in subclasses."""
        raise NotImplementedError


class Stage1InputParsing(PipelineStageBase):
    """Stage 1: Parse and understand user input."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_1_INPUT_PARSING)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Parse user input to extract intent, entities, and constraints."""
        user_input = context.user_input
        
        # Simple intent parsing (in production, use NLP/ML)
        intent = {
            "raw_input": user_input,
            "intent_type": self._classify_intent(user_input),
            "entities": self._extract_entities(user_input),
            "constraints": self._extract_constraints(user_input),
            "target_files": self._identify_target_files(user_input, context),
            "urgency": self._assess_urgency(user_input),
        }
        
        context.parsed_intent = intent
        return intent
    
    def _classify_intent(self, text: str) -> str:
        """Classify the user's intent."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["create", "add", "implement", "generate", "write"]):
            return "code_generation"
        elif any(kw in text_lower for kw in ["refactor", "restructure", "reorganize", "clean up"]):
            return "refactoring"
        elif any(kw in text_lower for kw in ["fix", "bug", "error", "issue", "broken"]):
            return "bug_fix"
        elif any(kw in text_lower for kw in ["review", "audit", "check", "analyze"]):
            return "code_review"
        elif any(kw in text_lower for kw in ["document", "comment", "readme"]):
            return "documentation"
        elif any(kw in text_lower for kw in ["test", "spec", "coverage"]):
            return "test_generation"
        elif any(kw in text_lower for kw in ["architecture", "design", "pattern", "structure"]):
            return "architecture_decision"
        elif any(kw in text_lower for kw in ["security", "vulnerability", "secure"]):
            return "security_audit"
        elif any(kw in text_lower for kw in ["performance", "optimize", "slow", "fast"]):
            return "performance_optimization"
        return "general_query"
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract code entities mentioned in text."""
        # Simple pattern matching - in production use NER
        import re
        entities = []
        # Match class names (CamelCase)
        entities.extend(re.findall(r'\b[A-Z][a-zA-Z0-9]*\b', text))
        # Match function names (snake_case)
        entities.extend(re.findall(r'\b[a-z_][a-z0-9_]*\b', text))
        # Filter common words
        common_words = {"the", "and", "or", "but", "for", "with", "from", "to", "in", "on", "at", "by"}
        return [e for e in entities if e.lower() not in common_words and len(e) > 2]
    
    def _extract_constraints(self, text: str) -> List[str]:
        """Extract constraints from text."""
        constraints = []
        text_lower = text.lower()
        constraint_keywords = [
            "must", "should", "must not", "should not", "cannot", "can't",
            "require", "required", "requirement", "constraint", "limit",
            "only", "exactly", "prefer", "avoid", "forbid", "forbidden"
        ]
        for kw in constraint_keywords:
            if kw in text_lower:
                constraints.append(kw)
        return list(set(constraints))
    
    def _identify_target_files(self, text: str, context: PipelineContext) -> List[str]:
        """Identify target files mentioned in the input."""
        import re
        files = []
        # Match file paths
        files.extend(re.findall(r'[\w/\\]+\.\w+', text))
        # In production, match against actual project files
        return files
    
    def _assess_urgency(self, text: str) -> str:
        """Assess urgency level."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["urgent", "asap", "immediately", "critical", "production", "down"]):
            return "critical"
        elif any(kw in text_lower for kw in ["soon", "today", "this week", "priority"]):
            return "high"
        elif any(kw in text_lower for kw in ["when possible", "eventually", "someday", "low priority"]):
            return "low"
        return "normal"


class Stage2ContextRetrieval(PipelineStageBase):
    """Stage 2: Retrieve relevant context from cognitive model."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_2_CONTEXT_RETRIEVAL)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Retrieve relevant context from cognitive model."""
        if not context.cognitive_model or not context.parsed_intent:
            return {}
        
        intent = context.parsed_intent
        
        # Get context for the task
        task_description = f"{intent['intent_type']}: {context.user_input}"
        cognitive_context = context.cognitive_model.get_context_for_task(task_description)
        
        # Also query the query engine for specific information
        query_results = {}
        if context.query_engine:
            # Semantic search for relevant code
            query_results["semantic"] = context.query_engine.execute_query(
                QueryType.SEMANTIC_SEARCH,
                {"query": context.user_input, "top_k": 20}
            ).results
            
            # Get relevant patterns
            query_results["patterns"] = context.query_engine.execute_query(
                QueryType.PATTERN_MATCH,
                {"pattern": "all"}
            ).results
            
            # Cross-layer analysis if relevant
            if intent["intent_type"] in ["refactoring", "architecture_decision", "code_generation"]:
                target_files = intent.get("target_files", [])
                first_file = target_files[0] if target_files else ""
                query_results["cross_layer"] = context.query_engine.execute_query(
                    QueryType.CROSS_LAYER,
                    {"query": "physical_to_business", "file_path": first_file}
                ).results
        
        # Combine contexts
        context.retrieved_context = {
            "cognitive_context": cognitive_context,
            "query_results": query_results,
            "relevant_entities": cognitive_context.get("entities", []),
            "relevant_triples": cognitive_context.get("triples", []),
            "business_rules": cognitive_context.get("business_rules", []),
        }
        
        return context.retrieved_context


class Stage3TaskClassification(PipelineStageBase):
    """Stage 3: Classify task type and determine approach."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_3_TASK_CLASSIFICATION)
    
    def run(self, context: PipelineContext) -> TaskType:
        """Classify the task type."""
        intent = context.parsed_intent
        intent_type = intent.get("intent_type", "general_query")
        
        # Map intent to TaskType
        type_mapping = {
            "code_generation": TaskType.CODE_GENERATION,
            "refactoring": TaskType.REFACTORING,
            "bug_fix": TaskType.BUG_FIX,
            "code_review": TaskType.CODE_REVIEW,
            "documentation": TaskType.DOCUMENTATION,
            "test_generation": TaskType.TEST_GENERATION,
            "architecture_decision": TaskType.ARCHITECTURE_DECISION,
            "security_audit": TaskType.SECURITY_AUDIT,
            "performance_optimization": TaskType.PERFORMANCE_OPTIMIZATION,
        }
        
        task_type = type_mapping.get(intent_type, TaskType.CODE_GENERATION)
        context.task_type = task_type
        
        return task_type


class Stage4PromptConstruction(PipelineStageBase):
    """Stage 4: Build optimal prompt using PromptEngine."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_4_PROMPT_CONSTRUCTION)
    
    def run(self, context: PipelineContext) -> GeneratedPrompt:
        """Construct optimal prompt using PromptEngine."""
        if not context.prompt_engine or not context.task_type:
            return GeneratedPrompt(system_prompt="", user_prompt="", context=None, estimated_tokens=0)
        
        intent = context.parsed_intent
        
        # Build metadata for prompt
        metadata = {
            "requirements": intent.get("constraints", []),
            "current_code": intent.get("current_code", ""),
        }
        
        # Add file-specific context if target files identified
        if intent.get("target_files"):
            metadata["target_files"] = intent["target_files"]
        
        # Generate prompt
        prompt = context.prompt_engine.generate_prompt(
            task_type=context.task_type,
            task_description=context.user_input,
            metadata=metadata,
        )
        
        context.generated_prompt = prompt
        return prompt


class Stage5PreValidation(PipelineStageBase):
    """Stage 5: Pre-execution validation using GuardEngine."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_5_PRE_VALIDATION)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Run pre-execution validation."""
        if not context.guard_engine or not context.generated_prompt:
            return {"passed": True, "issues": []}
        
        # Extract proposed changes from LLM response (if available) or from prompt
        proposed_changes = self._extract_proposed_changes(context)
        
        if proposed_changes:
            pre_validation = context.guard_engine.validate_proposed_change(proposed_changes)
            context.pre_validation = pre_validation
            
            return {
                "passed": pre_validation.approved,
                "issues": [i.to_dict() for i in pre_validation.pre_validation.issues],
                "risk_level": pre_validation.risk_assessment.risk_level.value if pre_validation.risk_assessment else "unknown",
            }
        
        return {"passed": True, "issues": []}
    
    def _extract_proposed_changes(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Extract proposed changes from context."""
        # In a real implementation, this would parse the LLM response
        # For now, return a structured representation based on intent
        intent = context.parsed_intent
        return {
            "files_affected": intent.get("target_files", []),
            "change_types": [context.task_type.value] if context.task_type else [],
            "change_types": [context.task_type.value] if context.task_type else [],
            "public_api_changes": 0,
            "test_coverage": 0.8,
            "dependency_depth": 2,
        }


class Stage6LLMExecution(PipelineStageBase):
    """Stage 6: Execute with LLM using real LLM client."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_6_LLM_EXECUTION)
    
    def run(self, context: PipelineContext) -> str:
        """Execute LLM with generated prompt."""
        if not context.generated_prompt:
            return ""
        
        if not context.llm_client:
            # Try to create LLM client from config
            if context.llm_config:
                context.llm_client = LLMClientFactory.create(context.llm_config)
            else:
                # Try default Ollama
                try:
                    context.llm_client = LLMClientFactory.create_from_env()
                except Exception:
                    return self._simulate_llm_response(context.generated_prompt)
        
        if not context.llm_client or not context.llm_client.is_available():
            context.warnings.append("LLM client not available, using simulation")
            return self._simulate_llm_response(context.generated_prompt)
        
        # Prepare messages for LLM
        prompt = context.generated_prompt
        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": prompt.user_prompt},
        ]
        
        # Execute LLM with retry
        try:
            from brain.llm.config import LLMMessage
            llm_messages = [
                LLMMessage(role="system", content=prompt.system_prompt),
                LLMMessage(role="user", content=prompt.user_prompt),
            ]
            
            # Use generate_with_retry for robustness
            if hasattr(context.llm_client, 'generate_with_retry'):
                response = context.llm_client.generate_with_retry(llm_messages)
            else:
                response = context.llm_client.generate(llm_messages)
            
            context.llm_response = response.content
            return response.content
            
        except Exception as e:
            context.warnings.append(f"LLM execution failed: {e}, using simulation")
            return self._simulate_llm_response(prompt)
    
    def _simulate_llm_response(self, prompt: GeneratedPrompt) -> str:
        """Simulate LLM response for testing/fallback."""
        return f"# Simulated LLM Response\n\nBased on the prompt for {prompt.context.task_type.value if prompt.context else 'unknown'}, here's the generated code:\n\n```python\n# TODO: Implement actual LLM integration\npass\n```"


class Stage7PostValidation(PipelineStageBase):
    """Stage 7: Post-execution validation using GuardEngine."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_7_POST_VALIDATION)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Run post-execution validation."""
        if not context.guard_engine:
            return {"passed": True, "results": []}
        
        # Get changed files from execution result
        changed_files = []
        if context.execution_result:
            changed_files = context.execution_result.get("changed_files", [])
        
        if changed_files:
            post_validation = context.guard_engine.validate_applied_change(
                change_id=context.pipeline_id,
                changed_files=changed_files,
            )
            context.post_validation = post_validation
            
            return {
                "passed": post_validation.approved,
                "results": [
                    {
                        "type": r.validation_type.value,
                        "passed": r.passed,
                        "message": r.message,
                        "errors": r.errors,
                        "warnings": r.warnings,
                    }
                    for r in post_validation.post_validation
                ],
            }
        
        return {"passed": True, "results": []}


class Stage8RiskAssessment(PipelineStageBase):
    """Stage 8: Risk assessment using RiskEngine."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_8_RISK_ASSESSMENT)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Assess risk of the proposed changes."""
        if not context.guard_engine or not context.parsed_intent:
            return {"risk_level": "unknown", "score": 0.0}
        
        intent = context.parsed_intent
        proposed_changes = {
            "files_affected": intent.get("target_files", []),
            "change_types": [context.task_type.value] if context.task_type else [],
            "public_api_changes": 0,
            "test_coverage": 0.8,
            "dependency_depth": 2,
        }
        
        risk_assessment = context.guard_engine.risk_engine.assess_change(proposed_changes)
        context.risk_assessment = risk_assessment
        
        return {
            "risk_level": risk_assessment.risk_level.value,
            "score": risk_assessment.score,
            "factors": [
                {
                    "name": f.name,
                    "weight": f.weight,
                    "value": f.value,
                    "description": f.description,
                }
                for f in risk_assessment.factors
            ],
            "mitigations": risk_assessment.mitigation_suggestions,
        }


class Stage9Execution(PipelineStageBase):
    """Stage 9: Execute the changes (apply to filesystem)."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_9_EXECUTION)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Execute the changes."""
        if not context.llm_response:
            return {"success": False, "error": "No LLM response to execute"}
        
        # Parse LLM response and apply changes
        # This is a placeholder - real implementation would:
        # 1. Parse LLM response for code changes
        # 2. Create backup/snapshot
        # 3. Apply changes to files
        # 4. Run tests
        
        changed_files = self._apply_changes(context)
        
        context.execution_result = {
            "success": True,
            "changed_files": changed_files,
            "timestamp": datetime.now().isoformat(),
        }
        
        return context.execution_result
    
    def _apply_changes(self, context: PipelineContext) -> List[str]:
        """Apply code changes to filesystem."""
        # Placeholder - would parse LLM response and apply changes
        return []


class Stage10Learning(PipelineStageBase):
    """Stage 10: Learn from outcome and update cognitive model."""
    
    def __init__(self):
        super().__init__(PipelineStage.STAGE_10_LEARNING)
    
    def run(self, context: PipelineContext) -> Dict[str, Any]:
        """Learn from the execution outcome."""
        learning_feedback = {
            "pipeline_id": context.pipeline_id,
            "timestamp": datetime.now().isoformat(),
            "task_type": context.task_type.value if context.task_type else "unknown",
            "success": context.execution_result.get("success", False) if context.execution_result else False,
            "risk_level": context.risk_assessment.risk_level.value if context.risk_assessment else "unknown",
            "pre_validation_passed": context.pre_validation.approved if context.pre_validation else True,
            "post_validation_passed": context.post_validation.approved if context.post_validation else True,
            "duration_ms": sum(s.duration_ms for s in context.metadata.get("stage_results", [])) if hasattr(context, "metadata") else 0,
        }
        
        # Update cognitive model with outcome
        if context.cognitive_model and context.project_graph:
            self._update_cognitive_model(context, learning_feedback)
        
        # Store in SQLite for persistent learning
        if context.project_root:
            self._store_learning_feedback(context.project_root, learning_feedback)
        
        context.learning_feedback = learning_feedback
        return learning_feedback
    
    def _update_cognitive_model(self, context: PipelineContext, feedback: Dict[str, Any]):
        """Update cognitive model with execution outcome."""
        # Add evolution event for this change
        from brain.models.core import EvolutionEventEntity
        
        event = EvolutionEventEntity(
            commit_hash=f"pipeline_{context.pipeline_id}",
            timestamp=datetime.now().timestamp(),
            author="Project Brain Pipeline",
            message=f"AI-assisted {feedback['task_type']}: {context.user_input[:100]}",
            files_changed=context.execution_result.get("changed_files", []) if context.execution_result else [],
            event_type=feedback["task_type"],
            impact_score=feedback.get("risk_score", 1.0),
            related_issues=[],
        )
        
        context.project_graph.evolution_events.append(event)
    
    def _store_learning_feedback(self, project_root: Path, feedback: Dict[str, Any]):
        """Store learning feedback in SQLite."""
        try:
            storage = SQLiteStorage(project_root / ".brain" / "brain.db")
            # Store in a learning_feedback table
            # For now, just ensure the table exists
            storage.set_metadata(f"learning_{feedback['pipeline_id']}", feedback)
        except Exception:
            pass  # Silent fail for learning storage


class AIPipeline:
    """Main AI Pipeline orchestrator (13.1)."""
    
    def __init__(self, project_root: Path, llm_config: Optional[LLMConfig] = None):
        self.project_root = project_root
        self.llm_config = llm_config or LLMConfig()
        self.stages: List[PipelineStageBase] = []
        self._initialize_stages()
    
    def _initialize_stages(self):
        """Initialize all 10 pipeline stages."""
        self.stages = [
            Stage1InputParsing(),
            Stage2ContextRetrieval(),
            Stage3TaskClassification(),
            Stage4PromptConstruction(),
            Stage5PreValidation(),
            Stage6LLMExecution(),
            Stage7PostValidation(),
            Stage8RiskAssessment(),
            Stage9Execution(),
            Stage10Learning(),
        ]
    
    def run(self, user_input: str, project_graph: ProjectGraph, 
            cognitive_model: CognitiveProjectModel,
            query_engine: ComprehensiveQueryEngine,
            guard_engine: GuardEngine,
            prompt_engine: PromptEngine) -> PipelineContext:
        """Run the full 10-stage pipeline."""
        
        # Create LLM client
        llm_client = LLMClientFactory.create(self.llm_config)
        
        context = PipelineContext(
            user_input=user_input,
            project_root=self.project_root,
            project_graph=project_graph,
            cognitive_model=cognitive_model,
            query_engine=query_engine,
            guard_engine=guard_engine,
            prompt_engine=prompt_engine,
            llm_client=llm_client,
            llm_config=self.llm_config,
        )
        
        stage_results = []
        
        for stage in self.stages:
            context.current_stage = stage.name
            result = stage.execute(context)
            stage_results.append(result)
            
            # Capture LLM response from Stage 6
            if stage.name == PipelineStage.STAGE_6_LLM_EXECUTION and result.output:
                context.llm_response = result.output
            
            if not result.success:
                context.errors.append(f"Stage {stage.name.value} failed: {result.error}")
                # Continue pipeline even if stage fails (for learning)
        
        context.metadata["stage_results"] = stage_results
        context.metadata["total_duration_ms"] = sum(r.duration_ms for r in stage_results)
        
        return context


def create_pipeline(project_root: Path) -> AIPipeline:
    """Factory function to create the AI pipeline."""
    return AIPipeline(project_root)