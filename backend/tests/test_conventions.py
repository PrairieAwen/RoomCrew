"""验证用户要求的中文方法说明，避免后续维护时遗漏。"""

import ast
import re
from pathlib import Path


def test_all_python_methods_explain_background_and_steps() -> None:
    """因为中文背景和步骤是用户明确的维护约束，需要检查本项目维护的每个 Python 方法。"""
    # 1、只检查项目维护的源码和测试，不触碰第三方库。
    root = Path(__file__).resolve().parents[2]
    failures = []
    for folder in (root / "backend", root / "packaging"):
        for path in folder.rglob("*.py"):
            source = path.read_text("utf-8")
            tree = ast.parse(source)
            lines = source.splitlines()
            for item in ast.walk(tree):
                if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                doc = ast.get_docstring(item) or ""
                excluded = set()
                for child in ast.walk(item):
                    if child is not item and isinstance(
                        child, ast.FunctionDef | ast.AsyncFunctionDef
                    ):
                        excluded.update(range(child.lineno - 1, child.end_lineno))
                body = "\n".join(
                    line
                    for index, line in enumerate(lines)
                    if item.lineno <= index < item.end_lineno and index not in excluded
                )
                steps = [int(value) for value in re.findall(r"^\s*#\s*(\d+)、", body, re.MULTILINE)]
                if (
                    "因为" not in doc
                    or "需要" not in doc
                    or not steps
                    or steps != list(range(1, len(steps) + 1))
                ):
                    failures.append(f"{path.relative_to(root)}:{item.lineno}:{item.name}")
    # 2、把遗漏定位到方法，不以一个类的说明替代全部方法的背景。
    assert not failures, failures
