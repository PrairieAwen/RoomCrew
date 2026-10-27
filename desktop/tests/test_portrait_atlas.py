"""手绘图集、裁切元数据与核心动作资源验收。"""

import json
from pathlib import Path

import pytest
from PIL import Image

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.assets.schema import validate_manifest
from roomcrew_desktop.runtime import DesktopRuntime as Runtime


def portrait_manifest() -> tuple[dict, tuple[int, int]]:
    """因为样板应验证实际随附美术，需要读取正式 PNG 和清单而非临时占位图。"""
    # 1、路径固定在项目资源内，不读取用户的配置或图集。
    folder = Path(__file__).resolve().parents[2] / "desktop/ui/studio/assets/atelier-v1"
    with Image.open(folder / "atlas.png") as image:
        size = image.size
    return json.loads((folder / "avatar.json").read_text("utf-8")), size


async def test_hand_painted_sample_imports_without_changing_agent_definition(
    tmp_path: Path,
) -> None:
    """因为手绘样板需要在真实应用中可用，需要验证正式导入、64 帧、透明背景和独立人物绑定。"""
    # 1、按实际人工按钮入口导入，不构造替代图片或修改模型请求。
    runtime = Runtime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        imported = await runtime.import_avatar_portrait()
        asset = await runtime.avatar_asset(imported["id"])
        value = asset["manifest"]
        assert value["version"] == 2 and len(value["frame_rects"]) == 64
        assert {"walk", "run", "phone", "sit_down", "stand_up"} <= set(imported["actions"])
        directions = {clip["direction"] for clip in value["clips"] if clip["action"] == "run"}
        assert directions == {"se", "ne"} and value["mirror_west"] is True
        member = await runtime.save_member({"name": "手绘员工", "avatar_id": imported["id"]}, 0)
        assert "avatar:" not in json.dumps(runtime.accounts.binding(member["id"]))
        # 2、所有帧源区域不同且坐标合法，不能把一张静态头像复制成完整动画。
        regions = {tuple(item["rect"]) for item in value["frame_rects"]}
        assert len(regions) == 64
    finally:
        await runtime.close()


def test_trimmed_frame_schema_rejects_bad_rectangles_and_offsets() -> None:
    """因为裁切元数据仍是不可信输入，需要拒绝越界、布尔数值、未知字段和目标画布溢出。"""
    # 1、所有错误都在导入时失败，不交给每帧播放器修补。
    manifest, size = portrait_manifest()
    cases = [
        {"rect": [-1, 0, 40, 40], "offset": [0, 0]},
        {"rect": [True, 0, 40, 40], "offset": [0, 0]},
        {"rect": [size[0] - 5, 0, 40, 40], "offset": [0, 0]},
        {"rect": [0, 0, 513, 40], "offset": [0, 0]},
        {"rect": [0, 0, 40, 40], "offset": [191, 0]},
        {"rect": [0, 0, 40, 40], "offset": [0.5, 0]},
        {"rect": [0, 0, 40, 40], "offset": [0, 0], "script": "run"},
    ]
    for invalid in cases:
        value = {**manifest, "frame_rects": [invalid, *manifest["frame_rects"][1:]]}
        with pytest.raises(ValueError):
            validate_manifest(value, size)
    with pytest.raises(ValueError):
        validate_manifest({**manifest, "mirror_west": "true"}, size)
    # 2、版本含义明确；v1 不能混入新裁切含义，v2 必须完整提供矩形。
    with pytest.raises(ValueError):
        validate_manifest({**manifest, "version": 1}, size)
    with pytest.raises(ValueError):
        validate_manifest({key: val for key, val in manifest.items() if key != "frame_rects"}, size)


def test_sample_alpha_and_anchor_metadata_are_real() -> None:
    """因为美术品质不能只看清单名称，需要确认实际透明度、脚底对齐与独立的手绘帧内容。"""
    # 1、PNG 具有真实透明背景，不包含假棋盘底；每帧都实际拥有不透明人物内容。
    value, _ = portrait_manifest()
    folder = Path(__file__).resolve().parents[2] / "desktop/ui/studio/assets/atelier-v1"
    with Image.open(folder / "atlas.png") as image:
        assert image.mode == "RGBA" and image.getchannel("A").getextrema() == (0, 255)
        for frame in value["frame_rects"]:
            x, y, width, height = frame["rect"]
            alpha = image.getchannel("A").crop((x, y, x + width, y + height))
            assert alpha.getbbox() is not None
            assert 156 <= frame["offset"][1] + height <= 164
