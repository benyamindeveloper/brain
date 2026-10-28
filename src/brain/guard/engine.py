"""Main Guard Engine - orchestrates all validation layers."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from brain.guard.post_validator import PostExecutionValidator, PostValidationResult
from brain.guard.pre_validator import PreExecutionValidator, ValidationResult
from brain.guard.risk_engine import RecoveryEngine, RiskAssessment, RiskEngine, RiskLevel
from brain.models.core import ProjectGraph


@dataclass
class GuardContext:
    """Context for a guard validation run."""
    change_id: str
    timestamp: datetime
    proposed_changes: dict[str, Any]
    project_graph: ProjectGraph | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardResult:
    """Complete result of guard validation."""
    change_id: str
    timestamp: datetime
    pre_validation: ValidationResult
    risk_assessment: RiskAssessment
    post_validation: list[PostValidationResult] = field(default_factory=list)
    recovery_plan: object | None = None
    approved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def overall_passed(self) -> bool:
        return (self.pre_validation.passed and
                self.risk_assessment.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM) and
                all(p.passed for p in self.post_validation))

    def summary(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "timestamp": self.timestamp.isoformat(),
            "approved": self.approved,
            "overall_passed": self.overall_passed,
            "pre_validation": {
                "passed": self.pre_validation.passed,
                "issues": len(self.pre_validation.issues),
                "errors": len(self.pre_validation.get_errors()),
                "warnings": len(self.pre_validation.get_warnings()),
            },
            "risk": {
                "level": self.risk_assessment.risk_level.value,
                "score": self.risk_assessment.score,
                "message": self.risk_assessment.message,
            },
            "post_validation": [
                {
                    "type": p.validation_type.value,
                    "passed": p.passed,
                    "message": p.message,
                }
                for p in self.post_validation
            ],
        }


class GuardEngine:
    """Main orchestrator for AI Guard validation."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.pre_validator = PreExecutionValidator()
        self.post_validator = PostExecutionValidator(project_root)
        self.risk_engine = RiskEngine(project_root)
        self.recovery_engine = RecoveryEngine(project_root)
        self.project_graph: ProjectGraph | None = None

    def set_project_graph(self, project_graph: ProjectGraph):
        """Set the project graph for validation."""
        self.project_graph = project_graph
        self.pre_validator.set_project_graph(project_graph)

    def validate_proposed_change(self, proposed_changes: dict[str, Any]) -> GuardResult:
        """Validate a proposed AI change before execution."""
        change_id = str(uuid.uuid4())[:8]
        context = GuardContext(
            change_id=change_id,
            timestamp=datetime.now(),
            proposed_changes=proposed_changes,
            project_graph=self.project_graph
        )

        # Pre-execution validation
        pre_validation = self.pre_validator.run_full_validation(proposed_changes)

        # Risk assessment
        risk_assessment = self.risk_engine.assess_change(proposed_changes)

        # Create recovery plan if risk is high
        recovery_plan = None
        if risk_assessment.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            recovery_plan = self.recovery_engine.create_recovery_plan(change_id)

        return GuardResult(
            change_id=change_id,
            timestamp=datetime.now(),
            pre_validation=pre_validation,
            risk_assessment=risk_assessment,
            recovery_plan=recovery_plan,
            approved=self._should_approve(pre_validation, risk_assessment),
            metadata={"context": context.metadata}
        )

    def validate_applied_change(self, change_id: str, changed_files: list[str]) -> GuardResult:
        """Validate a change after it has been applied."""
        # Post-execution validation
        post_validation = self.post_validator.run_all_validations(changed_files)

        # Create a minimal result for post-validation
        return GuardResult(
            change_id=change_id,
            timestamp=datetime.now(),
            pre_validation=ValidationResult(),
            risk_assessment=RiskAssessment(risk_level=RiskLevel.LOW, score=0.0),
            post_validation=post_validation,
            approved=all(p.passed for p in post_validation),
        )

    def full_validation_cycle(self, proposed_changes: dict[str, Any],
                              apply_fn=None) -> GuardResult:
        """Run complete validation cycle: pre-validate, apply, post-validate."""
        # Pre-validation
        pre_result = self.validate_proposed_change(proposed_changes)

        if not pre_result.approved:
            return pre_result

        # Apply changes if function provided
        changed_files = []
        if apply_fn:
            changed_files = apply_fn(proposed_changes)

        # Create snapshot for recovery
        snapshot = self.recovery_engine.create_snapshot(pre_result.change_id)

        # Post-validation
        post_result = self.validate_applied_change(pre_result.change_id, changed_files)

        # Combine results
        combined = GuardResult(
            change_id=pre_result.change_id,
            timestamp=pre_result.timestamp,
            pre_validation=pre_result.pre_validation,
            risk_assessment=pre_result.risk_assessment,
            post_validation=post_result.post_validation,
            recovery_plan=pre_result.recovery_plan,
            approved=pre_result.approved and post_result.approved,
        )

        # Auto-rollback if post-validation fails
        if not post_result.approved and snapshot:
            recovery_result = self.recovery_engine.restore_snapshot(snapshot)
            combined.metadata["auto_rollback"] = recovery_result
            combined.approved = False

        return combined

    def _should_approve(self, pre_validation: ValidationResult, risk_assessment: RiskAssessment) -> bool:
        """Determine if change should be approved."""
        # Block on critical errors
        if not pre_validation.passed:
            return False

        # Block on critical risk
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return False

        # Allow low/medium risk with no errors
        return True
