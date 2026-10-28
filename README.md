# Project Brain

**Cognitive Context & Evolution Engine for AI-Assisted Development**

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![VS Code](https://img.shields.io/badge/VS%20Code-extension-orange.svg)](vscode-extension/)

---

## What Is Project Brain?

Project Brain is a **local-first cognitive engine** that builds a persistent mental model of your codebase. It bridges the gap between source code and AI understanding — transforming your project from a collection of files into a **living system** that remembers architecture, business rules, decisions, and evolution history.

Unlike current AI coding tools that perform shallow text retrieval (RAG), Project Brain builds a **multi-layered graph** representing:

- **Physical Layer** — files, folders, imports
- **Logical Layer** — classes, functions, interfaces
- **Architectural Layer** — layers, modules, services
- **Business Layer** — rules, constraints, workflows
- **Evolution Layer** — history, changes, decisions

## Why It Matters

Current AI coding assistants (Cursor, Copilot, Claude Code) suffer from:

- **Context Amnesia** — only see immediate chat or a few recently opened files
- **Architecture Blindness** — don't understand layered architecture or dependency rules
- **No Historical Memory** — don't know why code was written a certain way
- **Hallucination & Duplication** — generate code that already exists or violates rules
- **Breaking Changes** — suggest refactors that break builds or tests

Project Brain transforms AI from a code generator into a **co-architect** that respects your project's soul.

## Features

### Tier 1 — Context Engine (MVP)
- Repository scanning with `.gitignore` support
- Multi-language AST parsing (Python, JavaScript, TypeScript)
- Architecture detection (Layered, Clean, DDD, MVC, Repository, CQRS)
- Dependency analysis with circular dependency detection
- Business rule extraction from source code patterns
- Git history analysis and evolution tracking
- Context compression for LLM consumption
- Output: `.brain-context.md` and `.brain-context.json`

### Tier 2 — AI Guard & Validation
- **Pre-execution validation**: duplicate detection, architecture rules, business rules, dependency conflicts
- **Post-execution validation**: compilation check, test execution, security scan, architecture drift detection
- **Risk Engine**: multi-factor risk scoring (Low/Medium/High/Critical)
- **Recovery Engine**: Git-based auto-rollback on failure
- VS Code extension for real-time validation

### Tier 3 — Cognitive Memory
- Knowledge Graph with semantic triples (2400+ extracted)
- Vector embeddings for semantic similarity search
- Memory Layers (Ephemeral, Short-term, Long-term, Semantic)
- 10-stage AI pipeline with context retrieval and validation
- Context compression with 4 strategies
- Refactoring detection from Git history
- Full SQLite persistence across sessions

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/project-brain.git
cd project-brain

# Install with dev dependencies
pip install -e ".[dev,test]"

# Install VS Code extension (optional)
cd vscode-extension
npm install
code --install-extension .
```

### Scan Your Project

```bash
# Scan current directory and generate context
brain scan .

# Output files:
# - .brain-context.md  (human-readable, for LLMs)
# - .brain-context.json (structured data)
```

### Use with AI

Copy the generated context and paste it into your AI tool:

```bash
cat .brain-context.md | pbcopy  # macOS
# or
type .brain-context.md | clip   # Windows
```

Then ask:
> "Now you know my entire codebase. Help me refactor the payment module to use the repository pattern."

### VS Code Extension

1. Open VS Code
2. Press `Ctrl+Shift+X` (Extensions)
3. Search for "Project Brain"
4. Install and activate

The extension provides:
- Real-time validation diagnostics
- Architecture, business rules, and evolution tree views
- One-click context generation
- Pre-commit hook integration

## CLI Commands

```bash
# Scan a project
brain scan [path] [--output DIR] [--format md|json|both]

# Show project structure tree
brain structure [path]

# Show language statistics
brain languages [path]

# AI Guard validation
brain guard validate changes.json
brain guard check changes.json
brain guard post-validate --files src/*.py
```

## Architecture

```
User Machine
├── brain CLI (Python)
├── Project Brain Core
├── Local LLM (optional - llama.cpp)
└── .brain cache directory
```

See `Project_Brain_SDS.docx` for the full architectural specification.

## Performance Targets

| Metric | Target |
|--------|--------|
| Initial Scan | 10K files in < 5s |
| Incremental Scan | < 100ms per file |
| Context Generation | 100K LOC → 50KB in 50s |
| Memory Usage | < 200MB for 1M LOC |
| Disk Usage | < 5% of repo size |

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src/brain --cov-report=html
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Contributions are welcome! Please open an issue or pull request.