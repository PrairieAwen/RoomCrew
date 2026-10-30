"""素材导入边界、事实动作提示和可丢弃线索验收。"""

import io
import json
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.assets.library import AvatarLibrary, normalize_png
from roomcrew_desktop.assets.schema import validate_manifest
from roomcrew_desktop.presentation.animation import animation_hint, visual_cue
from roomcrew_desktop.presentation.scene import SceneStore
from roomcrew_desktop.runtime import DesktopRuntime as Runtime


def avatar_fixture(folder: Path) -> Path:
    """因为测试不能依赖用户私有美术，需要生成明确用于回归的小型 PNG 图集与清单。"""
    # 1、所有颜色块只作为选帧证据，不进入生产默认美术。
    folder.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (256, 256), (60, 125, 91, 255))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("comment", "不应随规范化素材传播的私有描述")
    image.save(folder / "sheet.png", pnginfo=metadata)
    manifest = {
        "format": "roomcrew.avatar",
        "version": 1,
        "name": "回归素材",
        "image": "sheet.png",
        "frame_size": [64, 128],
        "pivot": [32, 120],
        "pixel_art": False,
        "clips": [
            {
                "action": "idle",
                "direction": "se",
                "posture": "standing",
                "expression": "neutral",
                "frames": [0, 1],
                "fps": 12,
                "loop": True,
            },
            {
                "action": "run",
                "direction": "e",
                "posture": "standing",
                "expression": "curious",
                "frames": [2, 3],
                "fps": 24,
                "loop": True,
            },
        ],
    }
    path = folder / "avatar.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")
    return path


def test_material_is_normalized_content_addressed_and_persistent(tmp_path: Path) -> None:
    """因为导入后素材不应依赖原文件夹，需要验证复制、去重、元数据清理及重开读取。"""
    # 1、同内容导入只保存一个包，输出不含用户原始路径。
    source = avatar_fixture(tmp_path / "source")
    library = AvatarLibrary(tmp_path / "library")
    first = library.import_manifest(source)
    assert library.import_manifest(source)["id"] == first["id"]
    assert len(library.catalog()) == 2
    stored = tmp_path / "library" / first["id"].split(":")[1]
    with Image.open(stored / "atlas.png") as picture:
        assert not picture.info and picture.size == (256, 256)
    # 2、重新实例化仍读取完整素材，修改后的图集不能继续使用旧 hash 身份。
    result = AvatarLibrary(tmp_path / "library").asset(first["id"])
    assert result["image_data"].startswith("data:image/png;base64,")
    assert "source" not in json.dumps(result)
    (stored / "atlas.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="修改"):
        library.asset(first["id"])


@pytest.mark.parametrize(
    "image", ["../private.png", "https://example.org/p.png", "C:\\key.png", "NUL.png"]
)
def test_import_rejects_paths_and_devices(tmp_path: Path, image: str) -> None:
    """因为素材清单属于不可信数据，需要在读取前拒绝跨目录、远程与系统设备引用。"""
    # 1、不能把图片导入接口变成任意文件读取入口。
    path = avatar_fixture(tmp_path / "source")
    value = json.loads(path.read_text("utf-8"))
    value["image"] = image
    path.write_text(json.dumps(value), "utf-8")
    with pytest.raises(ValueError):
        AvatarLibrary(tmp_path / "library").import_manifest(path)
    assert not (tmp_path / "library").exists()


def test_manifest_rejects_executable_or_invalid_frames(tmp_path: Path) -> None:
    """因为图集只允许动作数据，需要验证脚本字段、越界帧号、布尔帧号与重复变体失败。"""
    # 1、每次独立生成值，拒绝失败时不修改之前的清单。
    value = json.loads(avatar_fixture(tmp_path / "source").read_text("utf-8"))
    for field in ("script", "url", "permission"):
        with pytest.raises(ValueError):
            validate_manifest({**value, field: "execute"}, (256, 256))
    for invalid in (True, 999, -1, 1.5):
        copy = json.loads(json.dumps(value))
        copy["clips"][0]["frames"] = [invalid]
        with pytest.raises(ValueError):
            validate_manifest(copy, (256, 256))
    copy = json.loads(json.dumps(value))
    copy["clips"].append(copy["clips"][0])
    with pytest.raises(ValueError, match="重复"):
        validate_manifest(copy, (256, 256))


def test_png_dimensions_and_filetype_are_bounded() -> None:
    """因为压缩图片可以解码成大对象，需要验证尺寸上限和非 PNG 类型在加载前失败。"""
    # 1、像素超过边界和错误类型均不能作为图集注册。
    output = io.BytesIO()
    Image.new("RGBA", (2049, 32)).save(output, "PNG")
    with pytest.raises(ValueError):
        normalize_png(output.getvalue())
    output = io.BytesIO()
    Image.new("RGB", (64, 128)).save(output, "JPEG")
    with pytest.raises(ValueError):
        normalize_png(output.getvalue())


def test_animation_mapping_uses_real_tools_and_keeps_question_expression() -> None:
    """因为普通工具统一表现为操作电脑，需要验证读写共用工作姿态且人工提醒保持独立。"""
    # 1、文件读写与代码编辑都打电脑，问题和错误仍使用各自的表情通道。
    assert animation_hint("executing", ["write_file"], 0, 0)["gesture"] == "type"
    assert animation_hint("executing", ["read_file"], 0, 0)["gesture"] == "type"
    hint = animation_hint("executing", ["edit_file"], 1, 0)
    assert hint["gesture"] == "type" and hint["expression"] == "curious"
    assert animation_hint("executing", ["read_file"], 0, 1)["expression"] == "concerned"
    # 2、线索只包含有限元数据，原始工具正文、模型文本和权限均不能进入动画合同。
    cue = visual_cue(
        {
            "kind": "tool.started",
            "payload": {"name": "read_file", "input": "隐私正文"},
            "seq": 9,
            "member_id": "assistant",
            "run_id": "r",
            "created_at": "2026-10-26T00:00:00Z",
        }
    )
    assert cue and cue["action"] == "type" and cue["visual_only"]
    assert "隐私正文" not in json.dumps(cue, ensure_ascii=False)


async def test_material_binding_is_persisted_outside_agent_context(tmp_path: Path) -> None:
    """因为用户外观属于人物而非 Agent 提示，需要验证绑定持久化且不进入执行定义。"""
    # 1、导入与绑定无需真实模型，仍走生产运行时的人工接口。
    source = avatar_fixture(tmp_path / "source")
    runtime = Runtime(AppPaths.create(tmp_path / "runtime"))
    await runtime.start()
    try:
        imported = await runtime.import_avatar(str(source))
        member = await runtime.save_member({"name": "图集成员", "avatar_id": imported["id"]}, 0)
        assert (await runtime.member(member["id"]))["avatar_id"] == imported["id"]
        assert "avatar:" not in json.dumps(runtime.accounts.binding(member["id"]))
    finally:
        await runtime.close()


async def test_packaged_example_is_a_complete_importable_material(tmp_path: Path) -> None:
    """因为用户应有无需自行补图的制作起点，需要验证真实随附样例包含所有基础动作。"""
    # 1、通过与桌面按钮相同的入口导入，不使用测试颜色块代替正式样例。
    runtime = Runtime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        imported = await runtime.import_avatar_example()
        asset = await runtime.avatar_asset(imported["id"])
        actions = {clip["action"] for clip in asset["manifest"]["clips"]}
        assert {"run", "walk", "ask", "alert", "read", "write", "sit_down", "stand_up"} <= actions
        assert len(asset["manifest"]["clips"]) == 37
    finally:
        await runtime.close()


def test_display_path_replan_validates_observed_start(tmp_path: Path) -> None:
    """因为快速改目的地会提交当前地面格，需要验证重规划仍拒绝越界和穿家具的起点。"""
    # 1、合法观察点可重规划，输出仍是表现计划而不是执行命令。
    scene = SceneStore(tmp_path / "scene.sqlite")
    scene.snapshot([{"id": "boss"}])
    assert scene.move("boss", "sofa", 1, [0, 0])["route"][0] == [0, 0]
    for invalid in ([-1, 0], [1000, 0], [True, 0], [0.5, 0], [3, 2]):
        with pytest.raises(ValueError):
            scene.move("boss", "boss-desk", 1, invalid)
    scene.close()
