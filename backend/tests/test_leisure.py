"""空闲配置、跨上下文判定和素材边界的回归。"""

import json
from pathlib import Path

import pytest
from test_avatar_assets import avatar_fixture
from test_studio import event

from roomcrew.accounts.service import AccountService
from roomcrew.assets.library import AvatarLibrary
from roomcrew.presentation.reducer import actor_view, reduce_event
from roomcrew.storage.accounts import SqliteAccountRepository


def test_leisure_is_personal_persistent_and_outside_agent_context(tmp_path: Path) -> None:
    """因为共享 Agent 的人物仍有不同习惯，需要验证空闲配置独立持久化且不进入执行快照。"""
    # 1、引用同一 Agent 的新形象不能继承另一个形象的休闲选择。
    path = tmp_path / "accounts.sqlite"
    repository = SqliteAccountRepository(path)
    service = AccountService(repository)
    first = service.save({"name": "手机员工", "leisure_action": "phone", "leisure_delay": 2})
    second = service.save(
        {
            "name": "园艺员工",
            "agent_id": first["agent_id"],
            "leisure_action": "water",
            "leisure_delay": 9,
        }
    )
    service.save({"id": first["id"], "leisure_action": "game"}, first["revision"])
    assert service.get(second["id"])["leisure_action"] == "water"
    assert "leisure" not in json.dumps(service.binding(first["id"]))
    repository.close()
    # 2、重开数据库仍保留各自的动作与等待时间，配置不进入共享 Agent 定义。
    repository = SqliteAccountRepository(path)
    service = AccountService(repository)
    assert service.get(first["id"])["leisure_action"] == "game"
    assert service.get(second["id"])["leisure_delay"] == 9
    repository.close()


def test_old_members_receive_defaults_without_writing_revision(tmp_path: Path) -> None:
    """因为升级不能要求用户重建人物，需要对旧 JSON 补默认值且不隐式写库或增加版本。"""
    # 1、直接保存旧版本允许的字段，模拟升级前的真实人物记录。
    repository = SqliteAccountRepository(tmp_path / "accounts.sqlite")
    repository.save(
        {
            "id": "legacy",
            "name": "旧人物",
            "role": "employee",
            "agent_id": None,
            "enabled": True,
            "archived": False,
        },
        0,
    )
    service = AccountService(repository)
    member = service.get("legacy")
    assert member["leisure_action"] == "game" and member["leisure_delay"] == 5
    assert member["revision"] == 1
    raw = next(item for item in repository.members() if item["id"] == "legacy")
    assert "leisure_action" not in raw
    assert service.get("guardian")["leisure_action"] == "none"
    repository.close()


def test_leisure_rejects_scripts_bad_delays_and_guardian_changes(tmp_path: Path) -> None:
    """因为生活动作不能提供脚本入口，需要验证有限词表、严格整数和基础设施身份约束。"""
    # 1、不接受外部地址、原型名称、布尔延迟、浮点数和越界值。
    repository = SqliteAccountRepository(tmp_path / "accounts.sqlite")
    service = AccountService(repository)
    for values in [
        {"leisure_action": "https://evil"},
        {"leisure_action": "__proto__"},
        *[{"leisure_delay": value} for value in (True, 0.5, -1, 121)],
        {"id": "guardian", "leisure_action": "phone"},
    ]:
        with pytest.raises(ValueError):
            service.save(values, 1 if values.get("id") == "guardian" else 0)
    repository.close()


def test_idle_eligibility_aggregates_every_run_and_keeps_bottlenecks() -> None:
    """因为单个任务结束不能让仍有工作的形象摸鱼，需要验证多个 Run、待人工和错误的聚合。"""
    # 1、另一个 Run 在途及人工等待时，即使没有工具执行也不是空闲。
    actors = {}
    for item in [
        event(1, "run.started"),
        event(2, "run.started", run="r2"),
        event(3, "run.completed"),
        event(4, "human.requested", run="r2", request_id="q"),
    ]:
        reduce_event(actors, item)
        assert not actor_view(actors["assistant"])["idle_eligible"]
    # 2、取消后确实没有工作可空闲；失败提醒仍阻止生活动作掩盖异常。
    reduce_event(actors, event(5, "run.cancelled", run="r2"))
    assert actor_view(actors["assistant"])["idle_eligible"]
    reduce_event(actors, event(6, "run.started", run="r3"))
    reduce_event(actors, event(7, "run.failed", run="r3"))
    assert not actor_view(actors["assistant"])["idle_eligible"]


@pytest.mark.parametrize("action", ["phone", "game", "water", "relax"])
def test_custom_atlas_accepts_data_only_leisure_clips(tmp_path: Path, action: str) -> None:
    """因为用户可以自绘摸鱼动作，需要让正式素材导入器接受对应语义片段而非执行素材代码。"""
    # 1、在受约束清单中加入一个休闲变体，通过真实导入和读取校验。
    source = avatar_fixture(tmp_path / "source")
    manifest = json.loads(source.read_text("utf-8"))
    manifest["clips"].append({**manifest["clips"][0], "action": action})
    source.write_text(json.dumps(manifest), "utf-8")
    library = AvatarLibrary(tmp_path / "library")
    identifier = library.import_manifest(source)["id"]
    assert any(clip["action"] == action for clip in library.asset(identifier)["manifest"]["clips"])
