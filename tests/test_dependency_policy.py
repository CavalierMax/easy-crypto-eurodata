from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dependencies_have_upper_bounds():
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = config["project"]["dependencies"]
    assert dependencies
    assert all("<" in requirement for requirement in dependencies)


def test_readme_documents_dependency_security_audit():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8").casefold()
    assert "pip-audit" in readme
    assert "pip_audit" in readme

