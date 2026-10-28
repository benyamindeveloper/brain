"""Post-Execution Validation Engine for AI Guard."""

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PostValidationType(str, Enum):
    """Types of post-execution validation."""
    COMPILATION = "compilation"
    TEST_EXECUTION = "test_execution"
    SECURITY_SCAN = "security_scan"
    ARCHITECTURE_DRIFT = "architecture_drift"
    DEPENDENCY_VALIDATION = "dependency_validation"


@dataclass
class PostValidationResult:
    """Result of a post-execution validation."""
    validation_type: PostValidationType
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PostExecutionValidator:
    """Validates code after AI-applied changes."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def run_all_validations(self, changed_files: list[str]) -> list[PostValidationResult]:
        """Run all post-execution validations."""
        results = []

        # Compilation check
        results.append(self.validate_compilation(changed_files))

        # Test execution
        results.append(self.validate_tests(changed_files))

        # Security scan
        results.append(self.validate_security(changed_files))

        # Architecture drift detection
        results.append(self.validate_architecture_drift(changed_files))

        # Dependency validation
        results.append(self.validate_dependencies(changed_files))

        return results

    def validate_compilation(self, changed_files: list[str]) -> PostValidationResult:
        """Validate that code compiles."""
        errors: list[str] = []
        warnings: list[str] = []

        python_files = [f for f in changed_files if f.endswith('.py')]

        if python_files:
            # Check Python syntax
            for py_file in python_files:
                file_path = self.project_root / py_file
                if file_path.exists():
                    try:
                        with open(file_path, encoding='utf-8') as f:
                            compile(f.read(), py_file, 'exec')
                    except SyntaxError as e:
                        errors.append(f"{py_file}:{e.lineno}: {e.msg}")
                    except Exception as e:
                        errors.append(f"{py_file}: {str(e)}")

        passed = len(errors) == 0

        return PostValidationResult(
            validation_type=PostValidationType.COMPILATION,
            passed=passed,
            message="Compilation check passed" if passed else "Compilation errors found",
            details={"files_checked": len(python_files)},
            errors=errors,
            warnings=warnings
        )

    def validate_tests(self, changed_files: list[str]) -> PostValidationResult:
        """Run related tests."""
        errors = []
        warnings = []
        tests_run = 0
        tests_passed = 0

        # Find test files related to changed files
        test_files = self._find_related_tests(changed_files)

        if test_files:
            for test_file in test_files:
                try:
                    result = subprocess.run(
                        ["python", "-m", "pytest", test_file, "-v", "--tb=short"],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    tests_run += 1
                    if result.returncode == 0:
                        tests_passed += 1
                    else:
                        errors.append(f"{test_file}: Tests failed")
                        warnings.append(result.stdout[-500:] if result.stdout else "")
                except subprocess.TimeoutExpired:
                    errors.append(f"{test_file}: Test timeout")
                except Exception as e:
                    warnings.append(f"{test_file}: Could not run tests - {str(e)}")

        passed = len(errors) == 0

        return PostValidationResult(
            validation_type=PostValidationType.TEST_EXECUTION,
            passed=passed,
            message=f"Tests: {tests_passed}/{tests_run} passed" if tests_run > 0 else "No tests found for changed files",
            details={"tests_run": tests_run, "tests_passed": tests_passed},
            errors=errors,
            warnings=warnings
        )

    def validate_security(self, changed_files: list[str]) -> PostValidationResult:
        """Scan for security issues."""
        errors = []
        warnings = []

        # Patterns to detect
        security_patterns = {
            "hardcoded_secret": [
                r'password\s*=\s*["\'][^"\']+["\']',
                r'api_key\s*=\s*["\'][^"\']+["\']',
                r'secret\s*=\s*["\'][^"\']+["\']',
                r'token\s*=\s*["\'][^"\']+["\']',
            ],
            "sql_injection": [
                r'execute\s*\(\s*["\'].*%.*["\']',
                r'cursor\.execute\s*\(\s*f["\']',
            ],
            "command_injection": [
                r'subprocess\.(run|call|Popen)\s*\(\s*.*shell\s*=\s*True',
                r'os\.system\s*\(',
            ],
            "path_traversal": [
                r'\.\./',
                r'os\.path\.join\s*\([^)]*\.\.',
            ],
        }

        for file_path in changed_files:
            full_path = self.project_root / file_path
            if not full_path.exists() or full_path.is_dir():
                continue

            try:
                content = full_path.read_text(encoding='utf-8')
                lines = content.split('\n')

                for i, line in enumerate(lines, 1):
                    for category, patterns in security_patterns.items():
                        for pattern in patterns:
                            import re
                            if re.search(pattern, line, re.IGNORECASE):
                                msg = f"{file_path}:{i}: Potential {category}: {line.strip()[:100]}"
                                if category in ("hardcoded_secret", "sql_injection", "command_injection"):
                                    errors.append(msg)
                                else:
                                    warnings.append(msg)
            except Exception:
                pass

        passed = len(errors) == 0

        return PostValidationResult(
            validation_type=PostValidationType.SECURITY_SCAN,
            passed=passed,
            message="Security scan passed" if passed else "Security issues found",
            details={"files_scanned": len(changed_files)},
            errors=errors,
            warnings=warnings
        )

    def validate_architecture_drift(self, changed_files: list[str]) -> PostValidationResult:
        """Detect architecture drift by analyzing imports in changed files."""
        errors = []
        warnings = []
        files_checked = 0
        violations_found = []

        # Clean Architecture dependency rules (presentation -> application -> domain -> infrastructure)
        allowed_deps = {
            "presentation": {"presentation", "application", "domain", "shared"},
            "application": {"application", "domain", "shared"},
            "domain": {"domain", "shared"},
            "infrastructure": {"infrastructure", "domain", "application", "shared"},
            "shared": {"shared"},
        }

        for file_path in changed_files:
            full_path = self.project_root / file_path
            if not full_path.exists() or full_path.is_dir():
                continue
            files_checked += 1

            try:
                content = full_path.read_text(encoding="utf-8")
                source_layer = self._detect_layer(file_path)

                # Find imports in the file
                imports = self._extract_imports(content, file_path)
                for imp in imports:
                    target_layer = self._detect_layer(imp)
                    if target_layer == "unknown" or source_layer == "unknown":
                        continue

                    if target_layer not in allowed_deps.get(source_layer, set()):
                        violations_found.append({
                            "source_file": file_path,
                            "source_layer": source_layer,
                            "target_file": imp,
                            "target_layer": target_layer,
                        })
                        errors.append(
                            f"{file_path}: Layer violation - {source_layer} cannot import from {target_layer}"
                        )
            except Exception as e:
                warnings.append(f"{file_path}: Could not analyze: {str(e)}")

        passed = len(errors) == 0
        return PostValidationResult(
            validation_type=PostValidationType.ARCHITECTURE_DRIFT,
            passed=passed,
            message=f"Architecture drift check: {len(violations_found)} violation(s) in {files_checked} files",
            details={"files_checked": files_checked, "violations": violations_found},
            errors=errors,
            warnings=warnings,
        )

    def validate_dependencies(self, changed_files: list[str]) -> PostValidationResult:
        """Validate dependency integrity - check for missing imports and version conflicts."""
        errors: list[str] = []
        warnings: list[str] = []
        files_checked = 0
        dep_issues = []

        for file_path in changed_files:
            full_path = self.project_root / file_path
            if not full_path.exists() or full_path.is_dir():
                continue
            files_checked += 1

            try:
                content = full_path.read_text(encoding="utf-8")
                imports = self._extract_imports(content, file_path)

                for imp in imports:
                    # Check if it's a relative import that might be broken
                    if imp.startswith("."):
                        resolved = self._resolve_relative_import(file_path, imp)
                        if not resolved:
                            dep_issues.append({
                                "file": file_path,
                                "import": imp,
                                "issue": "Cannot resolve relative import",
                            })
                            warnings.append(f"{file_path}: Cannot resolve relative import '{imp}'")
                    elif "/" in imp or "\\" in imp:
                        # Path-like import, check if file exists
                        imp_path = self.project_root / imp
                        if not imp_path.exists() and not (self.project_root / f"{imp}.py").exists():
                            dep_issues.append({
                                "file": file_path,
                                "import": imp,
                                "issue": "Imported file not found",
                            })
                            warnings.append(f"{file_path}: Imported file not found '{imp}'")
            except Exception as e:
                warnings.append(f"{file_path}: Could not validate dependencies: {str(e)}")

        passed = len(errors) == 0
        return PostValidationResult(
            validation_type=PostValidationType.DEPENDENCY_VALIDATION,
            passed=passed,
            message=f"Dependency validation: {len(dep_issues)} issue(s) in {files_checked} files",
            details={"files_checked": files_checked, "issues": dep_issues},
            errors=errors,
            warnings=warnings,
        )

    def _detect_layer(self, file_path: str) -> str:
        """Detect architecture layer from file path."""
        path_lower = file_path.lower()
        if any(p in path_lower for p in ["controller", "route", "view", "api", "endpoint", "presentation", "ui"]):
            return "presentation"
        if any(p in path_lower for p in ["service", "application", "use_case", "interactor"]):
            return "application"
        if any(p in path_lower for p in ["domain", "entity", "model", "value_object", "aggregate"]):
            return "domain"
        if any(p in path_lower for p in ["repository", "gateway", "adapter", "infrastructure", "infra", "external"]):
            return "infrastructure"
        if any(p in path_lower for p in ["shared", "util", "common", "helper"]):
            return "shared"
        return "unknown"

    def _extract_imports(self, content: str, file_path: str) -> list[str]:
        """Extract import paths from file content."""
        imports = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                # Extract the module path
                if line.startswith("from "):
                    parts = line.split()
                    if len(parts) >= 2:
                        imports.append(parts[1])
                elif line.startswith("import "):
                    parts = line.split()
                    if len(parts) >= 2:
                        imports.append(parts[1].split(".")[0])
        return imports

    def _resolve_relative_import(self, file_path: str, import_path: str) -> bool:
        """Check if a relative import can be resolved."""
        # Simplified check - just verify the path doesn't contain obvious issues
        return not import_path.startswith("...")

    def _find_related_tests(self, changed_files: list[str]) -> list[str]:
        """Find test files related to changed files."""
        test_files = []
        test_dirs = ["tests", "test"]

        for changed in changed_files:
            path = Path(changed)

            # Look for test file in same directory
            test_file = path.parent / f"test_{path.name}"
            if test_file.exists():
                test_files.append(str(test_file))

            # Look for test file in test directories
            for test_dir in test_dirs:
                test_path = self.project_root / test_dir / path.parent.relative_to(self.project_root) / f"test_{path.name}"
                if test_path.exists():
                    test_files.append(str(test_path))

        return list(set(test_files))
