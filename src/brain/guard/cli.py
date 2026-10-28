"""CLI commands for AI Guard."""

import json
from pathlib import Path

import click

from brain.guard.engine import GuardEngine
from brain.storage.sqlite_storage import SQLiteStorage


@click.group()
def guard():
    """AI Guard - Pre/Post execution validation for AI-assisted changes."""
    pass


@guard.command()
@click.argument("change_file", type=click.Path(exists=True, path_type=Path))
@click.option("--project-root", "-p", type=click.Path(exists=True, path_type=Path), default=".", help="Project root directory")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output file for validation result")
def validate(change_file: Path, project_root: Path, output: Path | None):
    """Validate a proposed change from JSON file."""
    # Load project graph from storage
    storage = SQLiteStorage(project_root / ".brain" / "brain.db")
    project_graph = storage.load_project_graph()

    # Load proposed changes
    with open(change_file) as f:
        proposed_changes = json.load(f)

    # Run guard validation
    guard_engine = GuardEngine(project_root)
    guard_engine.set_project_graph(project_graph)

    result = guard_engine.validate_proposed_change(proposed_changes)

    # Output result
    output_data = result.summary()
    output_json = json.dumps(output_data, indent=2)

    if output:
        output.write_text(output_json)
        click.echo(f"Validation result saved to {output}")
    else:
        click.echo(output_json)

    # Exit code based on approval
    if not result.approved:
        exit(1)


@guard.command()
@click.argument("change_file", type=click.Path(exists=True, path_type=Path))
@click.option("--project-root", "-p", type=click.Path(exists=True, path_type=Path), default=".", help="Project root directory")
@click.option("--apply/--dry-run", default=False, help="Actually apply the changes")
def check(change_file: Path, project_root: Path, apply: bool):
    """Full validation cycle for a proposed change."""
    # Load project graph
    storage = SQLiteStorage(project_root / ".brain" / "brain.db")
    project_graph = storage.load_project_graph()

    # Load proposed changes
    with open(change_file) as f:
        proposed_changes = json.load(f)

    guard_engine = GuardEngine(project_root)
    guard_engine.set_project_graph(project_graph)

    # Run full cycle
    if apply:
        # Would need an apply function
        click.echo("Apply not yet implemented, running dry-run")
        apply = False

    result = guard_engine.validate_proposed_change(proposed_changes)

    click.echo(f"Change ID: {result.change_id}")
    click.echo(f"Approved: {result.approved}")
    click.echo(f"Risk Level: {result.risk_assessment.risk_level.value}")
    click.echo(f"Risk Score: {result.risk_assessment.score}/10")
    click.echo(f"Pre-validation: {'PASSED' if result.pre_validation.passed else 'FAILED'}")

    if result.pre_validation.issues:
        click.echo("\nIssues:")
        for issue in result.pre_validation.issues:
            click.echo(f"  [{issue.severity.value.upper()}] {issue.message}")

    if result.risk_assessment.mitigation_suggestions:
        click.echo("\nMitigation suggestions:")
        for suggestion in result.risk_assessment.mitigation_suggestions:
            click.echo(f"  - {suggestion}")

    if not result.approved:
        exit(1)


@guard.command()
@click.option("--project-root", "-p", type=click.Path(exists=True, path_type=Path), default=".", help="Project root directory")
@click.option("--files", "-f", multiple=True, help="Changed files to validate")
def post_validate(project_root: Path, files: tuple):
    """Run post-execution validation on changed files."""
    if not files:
        # Try to get changed files from git
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        files = [f.strip() for f in result.stdout.split('\n') if f.strip()]

    if not files:
        click.echo("No changed files to validate")
        return

    click.echo(f"Validating {len(files)} changed files...")

    post_validator = PostExecutionValidator(project_root)
    results = post_validator.run_all_validations(list(files))

    all_passed = True
    for result in results:
        status = "PASSED" if result.passed else "FAILED"
        click.echo(f"\n{result.validation_type.value}: {status}")
        click.echo(f"  {result.message}")

        if result.errors:
            for error in result.errors:
                click.echo(f"  ERROR: {error}")
        if result.warnings:
            for warning in result.warnings:
                click.echo(f"  WARNING: {warning}")

        if not result.passed:
            all_passed = False

    if not all_passed:
        exit(1)


# Need to import PostExecutionValidator for the CLI
from brain.guard.post_validator import PostExecutionValidator
