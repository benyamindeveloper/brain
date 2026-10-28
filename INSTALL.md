# Installation Guide

## Python CLI (Core)

### Prerequisites
- Python 3.10 or higher
- pip (comes with Python, or install via `python -m ensurepip`)

### Step 1: Install the package

```bash
# Clone or download the repository
git clone https://github.com/your-org/project-brain.git
cd project-brain

# Install with dependencies
pip install -e ".[dev,test]"
```

This installs:
- Core dependencies: click, pydantic, pyyaml, networkx, gitpython, rich, pathspec, requests
- Tree-sitter for multi-language AST parsing
- Dev tools: pytest, ruff, flake8, mypy, pre-commit

### Step 2: Verify installation

```bash
brain --version
brain scan . --format md
```

### Step 3: Scan your project

```bash
# Scan current directory
brain scan .

# Scan a specific project
brain scan ./my-project

# Output only JSON
brain scan . --format json

# Skip incremental loading (full rescan)
brain scan . --full
```

Output files:
- `.brain-context.md` — Human-readable context for LLMs
- `.brain-context.json` — Structured data
- `.brain/brain.db` — SQLite persistent storage

## VS Code Extension

### Prerequisites
- Node.js 18+ and npm
- VS Code 1.80+

### Step 1: Install dependencies

```bash
cd vscode-extension
npm install
```

### Step 2: Compile the extension

```bash
npm run compile
```

### Step 3: Install in VS Code

**Option A: From VS Code Extensions panel**
1. Open VS Code
2. Press `Ctrl+Shift+X` (Extensions)
3. Click "Install from VSIX"
4. Select `vscode-extension/project-brain-0.1.0.vsix`

**Option B: Using code CLI**
```bash
code --install-extension ./vscode-extension/project-brain-0.1.0.vsix
```

**Option C: Build VSIX and install**
```bash
cd vscode-extension
npm install -g vsce
vsce package
code --install-extension project-brain-0.1.0.vsix
```

### Step 4: Activate

1. Open your project in VS Code
2. Run `brain scan .` in the terminal (or use the "Scan Workspace" command)
3. The extension will automatically detect `.brain/brain.db` and show views

## Pre-commit Hook

Enable automatic validation before commits:

```bash
# Install pre-commit framework
pip install pre-commit

# Install hooks
pre-commit install
```

Or enable from VS Code:
1. Open Settings (`Ctrl+,`)
2. Search for "Project Brain"
3. Enable "Enable Pre-commit Hook"

## Docker

```bash
docker build -t project-brain .
docker run -v $(pwd):/workspace -w /workspace project-brain brain scan .
```

## LLM Integration (Optional)

Project Brain supports local LLMs for AI-powered features:

### llama.cpp (Recommended)

```bash
pip install llama-cpp-python
```

Set the model path:
```bash
brain --config llama_cpp_model_path=/path/to/model.gguf scan .
```

### Ollama (Alternative)

```bash
# Install Ollama: https://ollama.com
ollama pull qwen2.5-coder:7b

# Configure in VS Code settings
# projectBrain.llmProvider: "ollama"
# projectBrain.ollamaHost: "http://localhost:11434"
```

## Troubleshooting

### "brain: command not found"
The `brain` executable should be in your Python Scripts directory. Add it to PATH:
```bash
# Linux/macOS
export PATH="$PATH:$(python -c 'import site; print(site.getusersitepackages())')"

# Windows
# Add Python Scripts to PATH via System Environment Variables
```

### "No module named brain"
```bash
pip install -e .
```

### "tree-sitter not available"
```bash
pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript
```

### "NetworkX not available"
```bash
pip install networkx
```

### Windows Rich console issues
Project Brain uses ASCII fallbacks for Windows console compatibility.

## Getting Help

- Issues: https://github.com/your-org/project-brain/issues
- Documentation: https://project-brain.dev/docs
- Email: team@project-brain.dev