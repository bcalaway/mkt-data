"""Static checks on dags/ (Airflow itself isn't installed in this image).

The platform's rules for app DAGs (docs/app-platform.md in nyc_pa_aws_gitops,
ADR-0031): ids start with the app's name and `__`, no dots; imports are
Airflow, the platform helper and the standard library only, because DAG
files run inside the shared Airflow, not in this app's image.
"""

import ast
import sys
from pathlib import Path

import pytest

DAGS = sorted((Path(__file__).resolve().parent.parent / "dags").rglob("*.py"))
ALLOWED_TOP = {"airflow", "home_platform_jobs", "__future__"} | set(sys.stdlib_module_names)


def test_there_are_dags():
    assert DAGS


@pytest.mark.parametrize("path", DAGS, ids=lambda p: p.name)
def test_imports_are_airflow_or_stdlib(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for n in names:
            assert n.split(".")[0] in ALLOWED_TOP, f"{path.name}: imports {n}"


@pytest.mark.parametrize("path", DAGS, ids=lambda p: p.name)
def test_dag_ids(path):
    tree = ast.parse(path.read_text())
    ids = [
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "dag_id" and isinstance(kw.value, ast.Constant)
    ]
    assert ids, f"{path.name}: no literal dag_id"
    for dag_id in ids:
        assert dag_id.startswith("mkt_data__"), dag_id
        assert "." not in dag_id and dag_id == dag_id.lower(), dag_id


def _is_task(decorator) -> bool:
    return "task" in (getattr(decorator, "id", ""), getattr(getattr(decorator, "func", None), "id", ""),
                      getattr(getattr(decorator, "value", None), "id", ""),
                      getattr(getattr(getattr(decorator, "func", None), "value", None), "id", ""))


def _defines_task(fn: ast.FunctionDef) -> bool:
    return any(isinstance(n, ast.FunctionDef) and n is not fn and any(_is_task(d) for d in n.decorator_list)
               for n in ast.walk(fn))


@pytest.mark.parametrize("path", DAGS, ids=lambda p: p.name)
def test_dag_functions_define_tasks(path):
    """A function decorated with @dag must build tasks, itself or through a helper it calls. Catches a
    helper slipped in between the decorator and the DAG's function, which turns the helper into the DAG
    (it happened in secmaster-svc #7)."""
    tree = ast.parse(path.read_text())
    builders = {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and _defines_task(n)}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(isinstance(d, ast.Call) and getattr(d.func, "id", "") == "dag" for d in node.decorator_list):
            calls = {getattr(n.func, "id", "") for n in ast.walk(node) if isinstance(n, ast.Call)}
            assert _defines_task(node) or calls & builders, f"{path.name}: @dag {node.name}() defines no @task"
