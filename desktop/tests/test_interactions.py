"""客户端专属的工具分类、泡泡和自定义映射验收。"""

from pathlib import Path

import pytest

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.accounts import interaction_profile
from roomcrew_desktop.assets.bindings import material_profile
from roomcrew_desktop.presentation.animation import animation_hint, visual_cue
from roomcrew_desktop.runtime import DesktopRuntime


def test_tool_categories_map_to_client_animations_only() -> None:
    """因为后端不能决定素材动作，需要在桌面适配器验证 MCP、技能与普通工具的独立映射。"""
    # 1、同一执行状态按可信工具分类显示不同动作，不分析模型自然语言。
    assert animation_hint("executing", ["any_name"], 0, 0, ["mcp"])["gesture"] == "phone"
    assert animation_hint("executing", ["read_file"], 0, 0, ["skill"])["gesture"] == "read"
    assert animation_hint("executing", ["execute_python"], 0, 0, ["python"])["gesture"] == "work"
    cue = visual_cue(
        {
            "seq": 1,
            "kind": "tool.started",
            "member_id": "assistant",
            "run_id": "run",
            "created_at": "2026-10-27T00:00:00Z",
            "payload": {"name": "arbitrary", "tool_kind": "mcp"},
        }
    )
    assert cue and cue["action"] == "phone"


async def test_bubbles_persist_on_member_without_entering_agent_snapshot(tmp_path: Path) -> None:
    """因为人物可自定义短提示但不能污染 Agent 上下文，需要验证持久化位置和真实终态泡泡。"""
    # 1、只生成合成产品事件，不调用真实模型或伪造工具执行。
    runtime = DesktopRuntime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        await runtime.save_member(
            {
                "id": "assistant",
                "interaction_profile": {
                    "question_bubble": "老板，帮我选一下。",
                    "completed_bubble": "整理好了，点我看结果。",
                    "action_overrides": {"completed": "listen"},
                },
            },
            (await runtime.member("assistant"))["revision"],
        )
        assert "bubble" not in str(runtime.accounts.binding())
        conversation = runtime.store.create_conversation("synthetic-profile-reference")
        run = runtime.store.begin(conversation["id"], "模拟展示", "synthetic-ui-only-request")
        runtime.store.finish(run, "completed", {})
        data = await runtime.studio_feed()
        actor = next(item for item in data["actors"] if item["member_id"] == "assistant")
        assert actor["bubble"] == "整理好了，点我看结果。"
        assert actor["animation"]["gesture"] == "listen"
        assert actor["conversation_id"] == conversation["id"]
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    "value",
    [
        {"question_bubble": ""},
        {"completed_bubble": "x" * 81},
        {"action_overrides": {"mcp": "executeShell"}},
        {"script": "evil"},
    ],
)
def test_interaction_profile_rejects_unregistered_actions(value: dict) -> None:
    """因为显示配置不能加载脚本或任意动作，需要拒绝超长短语和未知素材语义。"""
    # 1、校验不读取后端配置，也不执行任何命令。
    with pytest.raises(ValueError):
        interaction_profile(value)


async def test_shared_agent_has_independent_material_bindings_and_bubbles(tmp_path: Path) -> None:
    """因为同一 Agent 可绑定两个形象，需要验证素材帧和泡泡归属人物而非共享定义。"""
    from test_avatar_assets import avatar_fixture

    # 1、两个形象共享执行定义，但仅给第二个形象绑定自定义图集与完成帧。
    runtime = DesktopRuntime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        asset = runtime._avatars.import_manifest(avatar_fixture(tmp_path / "source"))
        manifest = runtime._avatars.clip_catalog(asset["id"])
        assert manifest
        clip = manifest["clips"][0]
        from roomcrew_desktop.assets.bindings import clip_key

        profile = {
            "version": 1,
            "avatar_id": asset["id"],
            "bindings": {
                "completed": {
                    "action": clip["action"],
                    "clip": clip_key(clip),
                    "frames": list(reversed(clip["frames"])),
                    "fps": 7,
                    "loop": False,
                }
            },
        }
        first = await runtime.member("assistant")
        second = await runtime.save_member(
            {
                "name": "第二形象",
                "agent_id": first["agent_id"],
                "avatar_id": asset["id"],
                "material_profile": profile,
                "interaction_profile": {"completed_bubble": "我是第二形象，我完成了。"},
            },
            0,
        )
        assert (await runtime.member("assistant"))["material_profile"]["bindings"] == {}
        assert "material_profile" not in str(runtime.accounts.binding(second["id"]))
        # 2、完成事件绑定第二个 member_id，不能回退到默认助手的素材或泡泡。
        conversation = runtime.store.create_conversation("synthetic-profile-reference")
        run = runtime.store.begin(
            conversation["id"],
            "显示测试",
            "second-member-ui-request",
            second["name"],
            second["agent_id"],
            second["id"],
        )
        runtime.store.finish(run, "completed", {})
        snapshot = await runtime.studio_feed()
        actor = next(item for item in snapshot["actors"] if item["member_id"] == second["id"])
        assert actor["bubble"] == "我是第二形象，我完成了。"
        assert actor["material_category"] == "completed"
        assert actor["animation"]["gesture"] == clip["action"]
        assert (await runtime.member(second["id"]))["material_profile"] == profile
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    "binding",
    [
        {"action": "phone", "clip": "missing", "frames": [0]},
        {"action": "idle", "clip": "idle.s.standing.neutral", "frames": [999]},
        {"action": "idle", "clip": "idle.s.standing.neutral", "frames": [True]},
    ],
)
def test_material_frames_require_the_selected_atlas(binding: dict) -> None:
    """因为切换图集不能误用旧帧，需要拒绝缺失变体、越界帧和布尔帧号。"""
    # 1、验证仅使用合成清单，不读取用户素材。
    manifest = {
        "version": 2,
        "frame_rects": [{}, {}],
        "clips": [
            {
                "action": "idle",
                "direction": "s",
                "posture": "standing",
                "expression": "neutral",
                "frames": [0, 1],
                "fps": 6,
                "loop": True,
            }
        ],
    }
    with pytest.raises(ValueError):
        material_profile({"bindings": {"completed": binding}}, "avatar:test", manifest)
