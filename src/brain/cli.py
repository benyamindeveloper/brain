"""Main CLI entry point for Project Brain."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn
from rich.table import Table

from brain.scanner.repository_scanner import RepositoryScanner
from brain.analyzer.multi_language_analyzer import AnalyzerFactory
from brain.generator.context_generator import ContextGenerator
from brain.models.core import Language, FileEntity
from brain.guard.cli import guard


console = Console(force_terminal=True, legacy_windows=False)


@click.group()
@click.version_option(version="0.1.0", prog_name="brain")
def cli():
    """Project Brain - Cognitive Context & Evolution Engine for AI-Assisted Development"""
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path), default=".")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output directory for context files")
@click.option("--name", "-n", type=str, default=None, help="Project name (defaults to directory name)")
@click.option("--max-tokens", type=int, default=8000, help="Max tokens for markdown output")
@click.option("--format", "fmt", type=click.Choice(["md", "json", "both"]), default="both", help="Output format")
@click.option("--ignore", "-i", multiple=True, help="Additional ignore patterns")
@click.option("--incremental/--full", default=True, help="Use incremental scanning (load from persistent storage)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def scan(path: Path, output: Optional[Path], name: Optional[str], max_tokens: int, fmt: str, ignore: tuple, incremental: bool, verbose: bool):
    """Scan a project and generate context files."""
    project_root = path.resolve()
    project_name = name or project_root.name
    output_dir = output or project_root

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]Project Brain[/bold blue] - Scanning [cyan]{project_name}[/cyan]")
    console.print(f"Root: {project_root}")
    console.print(f"Output: {output_dir}")
    console.print(f"Mode: {'Incremental' if incremental else 'Full'}")

    # Step 1: Create generator and try to load from storage
    generator = ContextGenerator(project_root, project_name, use_persistent_storage=incremental)

    if incremental:
        console.print("Loading from persistent storage...")
        loaded = generator.load_from_storage()
        if loaded:
            console.print(f"[green]Loaded[/green] {len(generator.project_graph.files)} files from storage")
        else:
            console.print("No existing storage found, performing full scan")

    # Step 2: Scan repository (only if not loaded or incremental=False)
    if not (incremental and generator.project_graph.files):
        console.print("Scanning repository...")
        scanner = RepositoryScanner(project_root, ignore_patterns=list(ignore))
        file_entities = scanner.scan()
        console.print(f"Found {len(file_entities)} source files")

        if not file_entities:
            console.print("[yellow]No source files found![/yellow]")
            return

        # Step 3: Analyze files
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing source code...", total=len(file_entities))

            for file_entity in file_entities:
                progress.update(task, advance=1, description=f"Analyzing {file_entity.relative_path}")

                # Create analyzer for file's language
                analyzer = AnalyzerFactory.create(file_entity.language)
                analyzed_file = analyzer.analyze(file_entity)

                # Add to generator
                generator.add_file_entity(analyzed_file)

                # Add extracted classes and functions
                for cls in analyzer.get_classes().values():
                    generator.add_class_entity(cls)
                for func in analyzer.get_functions().values():
                    generator.add_function_entity(func)

    # Step 3: Generate output
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating context files...", total=None)

        if fmt in ("md", "both"):
            md_path = output_dir / ".brain-context.md"
            generator.generate_markdown(md_path, max_tokens=max_tokens)
            console.print(f"[green]OK[/green] Generated {md_path}")

        if fmt in ("json", "both"):
            json_path = output_dir / ".brain-context.json"
            generator.generate_json(json_path)
            console.print(f"[green]OK[/green] Generated {json_path}")

    # Save to persistent storage
    if incremental:
        console.print("Saving to persistent storage...")
        generator.save_to_storage()
        console.print("[green]OK[/green] Saved to storage")

    # Summary
    _print_summary(generator, console, verbose)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path), default=".")
def structure(path: Path):
    """Show project structure tree."""
    project_root = path.resolve()
    scanner = RepositoryScanner(project_root)
    structure = scanner.get_project_structure()

    def print_tree(node: dict, prefix: str = "", is_last: bool = True):
        connector = "└── " if is_last else "├── "
        if node["type"] == "directory":
            console.print(f"{prefix}{connector}[bold]{node['name']}[/bold]/")
            children = node.get("children", [])
            for i, child in enumerate(children):
                print_tree(child, prefix + ("    " if is_last else "│   "), i == len(children) - 1)
        else:
            lang = node.get("language", "")
            console.print(f"{prefix}{connector}{node['name']} [dim]({lang})[/dim]")

    console.print(f"[bold]{structure['name']}[/bold]/")
    children = structure.get("children", [])
    for i, child in enumerate(children):
        print_tree(child, "", i == len(children) - 1)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path), default=".")
def languages(path: Path):
    """Show language statistics for the project."""
    project_root = path.resolve()
    scanner = RepositoryScanner(project_root)
    files = scanner.scan()

    stats = {}
    for f in files:
        lang = f.language.value
        if lang not in stats:
            stats[lang] = {"files": 0, "lines": 0, "size": 0}
        stats[lang]["files"] += 1
        stats[lang]["lines"] += f.lines_of_code
        stats[lang]["size"] += f.size_bytes

    table = Table(title="Language Statistics")
    table.add_column("Language", style="cyan")
    table.add_column("Files", justify="right")
    table.add_column("Lines of Code", justify="right")
    table.add_column("Size (KB)", justify="right")

    for lang, data in sorted(stats.items(), key=lambda x: x[1]["files"], reverse=True):
        table.add_row(lang, str(data["files"]), str(data["lines"]), f"{data['size'] / 1024:.1f}")

    console.print(table)


def _print_summary(generator: ContextGenerator, console: Console, verbose: bool):
    """Print analysis summary."""
    metadata = generator.project_graph.metadata

    table = Table(title="Analysis Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Project", metadata["project_name"])
    table.add_row("Files", str(metadata["total_files"]))
    table.add_row("Classes", str(metadata["total_classes"]))
    table.add_row("Functions", str(metadata["total_functions"]))
    table.add_row("Dependencies", str(metadata["total_dependencies"]))
    table.add_row("Languages", ", ".join(metadata["languages"]))
    table.add_row("Patterns", ", ".join(metadata["architecture_patterns"]) or "None")

    console.print(table)

    if verbose and generator.architecture_analysis:
        console.print("\n[bold]Architecture Layers:[/bold]")
        for layer, entity in generator.architecture_analysis.layers.items():
            if entity.files or entity.classes:
                console.print(f"  {layer.value}: {len(entity.files)} files, {len(entity.classes)} classes")

        if generator.dependency_graph:
            stats = generator.dependency_analyzer.get_dependency_stats(generator.dependency_graph)
            console.print("\n[bold]Dependency Stats:[/bold]")
            for k, v in stats.items():
                console.print(f"  {k}: {v}")


cli.add_command(guard)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()