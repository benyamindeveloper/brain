"""Risk Engine and Recovery Engine for AI Guard."""

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RiskLevel(str, Enum):
    """Risk levels for changes."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskFactor:
    """A factor contributing to risk assessment."""
    name: str
    weight: float
    value: float
    description: str


@dataclass
class RiskAssessment:
    """Complete risk assessment for a change."""
    risk_level: RiskLevel
    score: float  # 0.0 to 10.0
    factors: list[RiskFactor] = field(default_factory=list)
    message: str = ""
    mitigation_suggestions: list[str] = field(default_factory=list)


class RiskEngine:
    """Assesses risk level of proposed changes."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def assess_change(self, change_data: dict[str, Any]) -> RiskAssessment:
        """Assess risk of a proposed change."""
        factors = []

        # Factor 1: Change scope (files affected)
        num_files = len(change_data.get("files_affected", []))
        scope_score = min(num_files * 0.5, 5.0)
        factors.append(RiskFactor(
            name="change_scope",
            weight=1.0,
            value=scope_score,
            description=f"Number of files changed: {num_files}"
        ))

        # Factor 2: Change type
        change_types = change_data.get("change_types", [])
        type_weights = {
            "delete": 3.0,
            "modify": 1.5,
            "add": 1.0,
            "refactor": 2.0,
            "rename": 1.5,
        }
        type_score = sum(type_weights.get(t, 1.0) for t in change_types)
        factors.append(RiskFactor(
            name="change_type",
            weight=1.5,
            value=min(type_score, 5.0),
            description=f"Change types: {', '.join(change_types)}"
        ))

        # Factor 3: Core/central files
        core_patterns = ["core", "model", "entity", "base", "config", "security", "auth"]
        core_files = sum(1 for f in change_data.get("files_affected", [])
                         if any(p in f.lower() for p in core_patterns))
        core_score = min(core_files * 1.5, 4.0)
        factors.append(RiskFactor(
            name="core_files",
            weight=2.0,
            value=core_score,
            description=f"Core files affected: {core_files}"
        ))

        # Factor 4: Public API changes
        api_changes = change_data.get("public_api_changes", 0)
        api_score = min(api_changes * 1.0, 3.0)
        factors.append(RiskFactor(
            name="public_api",
            weight=1.5,
            value=api_score,
            description=f"Public API changes: {api_changes}"
        ))

        # Factor 5: Test coverage impact
        test_coverage = change_data.get("test_coverage", 1.0)
        coverage_risk = (1.0 - test_coverage) * 3.0
        factors.append(RiskFactor(
            name="test_coverage",
            weight=1.0,
            value=coverage_risk,
            description=f"Test coverage: {test_coverage:.0%}"
        ))

        # Factor 6: Dependency depth
        dep_depth = change_data.get("dependency_depth", 1)
        depth_score = min(dep_depth * 0.5, 2.0)
        factors.append(RiskFactor(
            name="dependency_depth",
            weight=1.0,
            value=depth_score,
            description=f"Dependency chain depth: {dep_depth}"
        ))

        # Calculate weighted score
        total_weight = sum(f.weight for f in factors)
        weighted_score = sum(f.value * f.weight for f in factors) / total_weight if total_weight > 0 else 0

        # Determine risk level
        if weighted_score >= 7.0:
            risk_level = RiskLevel.CRITICAL
        elif weighted_score >= 5.0:
            risk_level = RiskLevel.HIGH
        elif weighted_score >= 3.0:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # Generate mitigation suggestions
        mitigations = self._generate_mitigations(factors, risk_level)

        return RiskAssessment(
            risk_level=risk_level,
            score=round(weighted_score, 2),
            factors=factors,
            message=self._generate_message(risk_level, weighted_score),
            mitigation_suggestions=mitigations
        )

    def _generate_message(self, level: RiskLevel, score: float) -> str:
        messages = {
            RiskLevel.LOW: f"Low risk change (score: {score:.1f}/10) - safe to proceed",
            RiskLevel.MEDIUM: f"Medium risk change (score: {score:.1f}/10) - review recommended",
            RiskLevel.HIGH: f"High risk change (score: {score:.1f}/10) - requires approval",
            RiskLevel.CRITICAL: f"Critical risk change (score: {score:.1f}/10) - blocking required",
        }
        return messages.get(level, f"Risk score: {score:.1f}/10")

    def _generate_mitigations(self, factors: list, level: RiskLevel) -> list[str]:
        """Generate mitigation suggestions based on risk factors."""
        mitigations = []

        high_factors = [f for f in factors if f.value >= 3.0]
        for factor in high_factors:
            if factor.name == "core_files":
                mitigations.append("Run full test suite before merging")
                mitigations.append("Require code review from core team member")
            elif factor.name == "public_api":
                mitigations.append("Update API documentation")
                mitigations.append("Add deprecation warnings if breaking changes")
            elif factor.name == "change_scope":
                mitigations.append("Split into smaller, focused changes")
                mitigations.append("Add integration tests for affected components")
            elif factor.name == "test_coverage":
                mitigations.append("Add unit tests for new/modified code")
                mitigations.append("Run mutation testing to verify test quality")

        if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            mitigations.append("Require senior developer approval")
            mitigations.append("Deploy to staging for manual verification")

        return mitigations


@dataclass
class RecoveryPlan:
    """Plan for recovering from failed changes."""
    steps: list[str]
    commands: list[str]
    rollback_branch: str
    estimated_time: str


class RecoveryEngine:
    """Handles automatic rollback and recovery."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def create_recovery_plan(self, change_id: str) -> RecoveryPlan:
        """Create a recovery plan for a change."""
        # Get current git state
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            current_branch = branch_result.stdout.strip()

            # Create rollback branch name
            rollback_branch = f"rollback/{change_id}"

            steps = [
                f"1. Current branch: {current_branch}",
                f"2. Create rollback branch: {rollback_branch}",
                "3. Reset to previous commit",
                "4. Verify rollback",
            ]

            commands = [
                f"git checkout -b {rollback_branch}",
                "git reset --hard HEAD~1",
                "git push origin HEAD --force-with-lease",
            ]

            return RecoveryPlan(
                steps=steps,
                commands=commands,
                rollback_branch=rollback_branch,
                estimated_time="< 1 minute"
            )
        except Exception:
            return RecoveryPlan(
                steps=["Error creating recovery plan"],
                commands=[],
                rollback_branch="",
                estimated_time="N/A"
            )

    def execute_rollback(self, rollback_branch: str, target_commit: str | None = None) -> dict[str, Any]:
        """Execute rollback to a previous state."""
        try:
            # Checkout rollback branch
            subprocess.run(
                ["git", "checkout", rollback_branch],
                cwd=self.project_root,
                check=True,
                capture_output=True
            )

            # Reset to target commit or previous
            if target_commit:
                subprocess.run(
                    ["git", "reset", "--hard", target_commit],
                    cwd=self.project_root,
                    check=True,
                    capture_output=True
                )
            else:
                subprocess.run(
                    ["git", "reset", "--hard", "HEAD~1"],
                    cwd=self.project_root,
                    check=True,
                    capture_output=True
                )

            return {
                "success": True,
                "message": f"Rolled back to {target_commit or 'previous commit'}",
                "branch": rollback_branch
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "message": f"Rollback failed: {e.stderr}",
                "branch": rollback_branch
            }

    def create_snapshot(self, change_id: str) -> str:
        """Create a git snapshot before applying changes."""
        snapshot_tag = f"snapshot/{change_id}"

        try:
            subprocess.run(
                ["git", "tag", snapshot_tag],
                cwd=self.project_root,
                check=True,
                capture_output=True
            )
            return snapshot_tag
        except subprocess.CalledProcessError:
            return ""

    def restore_snapshot(self, snapshot_tag: str) -> dict[str, Any]:
        """Restore from a snapshot tag."""
        try:
            subprocess.run(
                ["git", "reset", "--hard", snapshot_tag],
                cwd=self.project_root,
                check=True,
                capture_output=True
            )
            return {"success": True, "message": f"Restored from {snapshot_tag}"}
        except subprocess.CalledProcessError as e:
            return {"success": False, "message": f"Restore failed: {e.stderr}"}
