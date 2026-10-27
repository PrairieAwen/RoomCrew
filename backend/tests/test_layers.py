"""用依赖规则保护分层，防止未来重新把 SDK、凭据和桌面混在一个文件。"""

import ast
from pathlib import Path

import pytest

from roomcrew.contracts.errors import ExecutionError
from roomcrew.mcp.provider import configured_mcp_tools
from roomcrew.security.paths import resolve_task_path
from roomcrew.tools.python import python_runtime

LAYERS = {
    "contracts": {"contracts"},
    "security": {"security", "contracts"},
    "config": {"config", "security"},
    "models": {"models", "config", "security", "middleware", "contracts"},
    "context_compression": {"context_compression"},
    "middleware": {"middleware", "context_compression", "contracts"},
    "tools": {"tools", "security", "contracts"},
    "mcp": {"mcp", "contracts"},
    "skills": {"skills", "security", "contracts"},
    "agent_loop": {"agent_loop", "tracing", "contracts"},
    "tracing": {"tracing"},
    "storage": {"storage"},
    "accounts": {"accounts", "contracts"},
    "platform": {"platform"},
}
LAYERS["application"] = set(LAYERS) | {"application"}


def test_internal_dependencies_obey_layer_contract() -> None:
    """因为目录分开仍可能反向依赖，需要自动检查每个内部导入是否符合已声明的模块边界。"""
    # 1、解析实际源码，包括方法内的延迟导入，不只检查文件顶层。
    root = Path(__file__).resolve().parents[1] / "src/roomcrew"
    failures = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if len(relative.parts) < 2:
            continue
        layer = relative.parts[0]
        for item in ast.walk(ast.parse(path.read_text("utf-8"))):
            names = []
            if isinstance(item, ast.ImportFrom) and item.module:
                names = [item.module]
            elif isinstance(item, ast.Import):
                names = [alias.name for alias in item.names]
            for name in names:
                if name.startswith(("roomcrew_desktop", "webview")):
                    failures.append(f"{relative} -> desktop dependency")
                if name.startswith("roomcrew.") and name.split(".")[1] not in LAYERS[layer]:
                    failures.append(f"{relative} -> {name}")
    # 2、Loop 不能读配置或数据库，桌面不能直接调用模型 SDK，安全模块不依赖应用用例。
    assert not failures, failures


def test_desktop_depends_only_on_application_contracts_and_paths() -> None:
    """因为桌面桥已独立成包，需要防止它绕过应用用例访问凭据、数据库或框架。"""
    # 1、检查实际导入；宿主引用后端仅限应用、合同与本机资源定位。
    root = Path(__file__).resolve().parents[2] / "desktop/src/roomcrew_desktop"
    failures = []
    for path in root.rglob("*.py"):
        for item in ast.walk(ast.parse(path.read_text("utf-8"))):
            names = []
            if isinstance(item, ast.ImportFrom) and item.module:
                names = [item.module]
            elif isinstance(item, ast.Import):
                names = [alias.name for alias in item.names]
            for name in names:
                if name.startswith("roomcrew.") and name.split(".")[1] not in {
                    "application",
                    "contracts",
                    "platform",
                    "accounts",
                }:
                    failures.append(f"{path.name} -> {name}")
                if name.startswith(("deepagents", "langchain", "langgraph")):
                    failures.append(f"{path.name} -> {name}")
                if name.startswith("sqlite3") and path.parent.name != "presentation":
                    failures.append(f"{path.name} -> non-presentation database access")
    assert not failures, failures


def test_framework_types_stay_in_adapters() -> None:
    """因为前端合同和用例不能绑定框架私有类型，需要限制 SDK 导入只能发生在适配职责内。"""
    # 1、存储 checkpoint、工具和模型属于明确适配边界，产品与桌面不直接导入 SDK。
    allowed = {
        "agent_loop",
        "models",
        "context_compression",
        "middleware",
        "tools",
        "mcp",
        "storage",
    }
    root = Path(__file__).resolve().parents[1] / "src/roomcrew"
    failures = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if relative.parts[0] in allowed:
            continue
        for item in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(item, ast.ImportFrom) and (item.module or "").startswith(
                ("deepagents", "langchain", "langgraph")
            ):
                failures.append(str(relative))
    assert not failures, failures


@pytest.mark.parametrize(
    "path", ["/../../private/model-config.dpapi", "C:\\private\\key", "/C:/key", "relative.txt"]
)
def test_shared_task_path_policy_rejects_host_paths(tmp_path: Path, path: str) -> None:
    """因为产物与 Skills 共同依赖任务路径检查，需要验证外部路径不能绕过统一入口。"""
    # 1、拒绝路径在真正读写之前发生，不需要创建敏感文件。
    with pytest.raises(ValueError):
        resolve_task_path(tmp_path, path)


async def test_empty_mcp_and_missing_python_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """因为能力入口不能静默回退，需要验证无配置不连接，缺少随包解释器时拒绝宿主执行。"""
    # 1、空服务器集合不创建连接或发现工具。
    assert await configured_mcp_tools([]) == []
    # 2、缺少冻结包资源不能改用宿主 Python 或 PATH 中其他解释器。
    import sys

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    with pytest.raises(ExecutionError, match="PYTHON_UNAVAILABLE"):
        python_runtime(tmp_path / "cache")
