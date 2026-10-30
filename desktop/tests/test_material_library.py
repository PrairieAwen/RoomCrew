"""完整美术库、多页图集与有限资源边界验收。"""

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.assets.library import AvatarLibrary
from roomcrew_desktop.assets.paths import atlas_filenames
from roomcrew_desktop.assets.schema import validate_manifest
from roomcrew_desktop.presentation.contracts import EXPRESSIONS, GESTURES
from roomcrew_desktop.runtime import DesktopRuntime as Runtime

LIBRARY = Path(__file__).resolve().parents[2] / "desktop/ui/studio/assets/library-v1"


def material_catalog() -> dict:
    """因为数量与覆盖必须取自真实交付，需要读取随应用分发的素材登记表。"""
    # 1、固定资源路径不读取本机账号或模型配置。
    return json.loads((LIBRARY / "catalog.json").read_text("utf-8"))


async def test_four_bundles_import_and_bind_outside_agent_context(tmp_path: Path) -> None:
    """因为整套素材要能用于真实人物，需要验证正式导入、持久化和配置隔离而非仅能看图。"""
    # 1、四种角色通过生产运行时导入，图像规范化和内容寻址均使用正式实现。
    runtime = Runtime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        for entry in material_catalog()["characters"]:
            imported = await runtime.import_avatar_bundle(entry["id"])
            asset = await runtime.avatar_asset(imported["id"])
            value = asset["manifest"]
            assert value["version"] == 3 and len(asset["image_pages"]) == 2
            if entry["id"] != "hippo":
                assert {clip["action"] for clip in value["clips"]} == GESTURES
                assert {
                    clip["expression"] for clip in value["clips"] if clip["action"] == "idle"
                } == EXPRESSIONS
            else:
                assert entry["coverage_level"] == "keyframe-preview"
                assert {"walk", "type", "phone", "ask", "report"} <= {
                    clip["action"] for clip in value["clips"]
                }
            assert len(value["frame_rects"]) == entry["frame_count"]
            assert {frame["page"] for frame in value["frame_rects"]} == {0, 1}
            member = await runtime.save_member(
                {"name": entry["name"], "avatar_id": imported["id"]}, 0
            )
            assert (await runtime.member(member["id"]))["avatar_id"] == imported["id"]
            assert "avatar:" not in json.dumps(runtime.accounts.binding(member["id"]))
        # 2、非注册角色不能把内部素材入口扩张为任意资源读取。
        with pytest.raises(ValueError):
            await runtime.import_avatar_bundle("../private")
    finally:
        await runtime.close()


def test_page_scale_and_image_name_boundaries() -> None:
    """因为新增图集页不能放宽不可信输入边界，需要拒绝第三页、越界矩形、非法缩放与文件名。"""
    # 1、使用真实素材清单逐项破坏；所有错误应在导入前失败。
    entry = material_catalog()["characters"][0]
    manifest = entry["manifest"]
    for changes in (
        {"page": 2},
        {"page": True},
        {"scale": True},
        {"scale": float("nan")},
        {"scale": 2.01},
        {"scale": 0.24},
        {"offset": [512, 512]},
        {"rect": [1250, 0, 10, 10]},
    ):
        value = copy.deepcopy(manifest)
        value["frame_rects"][0].update(changes)
        with pytest.raises(ValueError):
            validate_manifest(value, [(1254, 1254), (1254, 1254)])
    # 2、Windows 同名与设备规范化不能绕过目录约束。
    for names in (
        ["a.png", "A.PNG"],
        ["a.png", "b.png", "c.png"],
        ["../a.png"],
        ["NUL.png"],
        ["CON .png"],
        ["https://example.org/a.png"],
        ["a.png "],
    ):
        with pytest.raises(ValueError):
            atlas_filenames({"version": 3, "images": names})


def test_second_page_tampering_is_detected(tmp_path: Path) -> None:
    """因为工作动作页也参与角色身份，需要验证第二页遭替换后旧内容标识立即失效。"""
    # 1、真实导入后只修改测试库，不触碰随程序分发的原图。
    library = AvatarLibrary(tmp_path / "library")
    imported = library.import_manifest(LIBRARY / "characters/assistant/avatar.json")
    library.asset(imported["id"])
    folder = library.root / imported["id"].split(":")[1]
    (folder / "atlas-1.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="修改"):
        library.asset(imported["id"])


def test_catalog_matches_real_images_and_object_regions() -> None:
    """因为完整素材不能靠数量说明代替，需要核对实际透明 PNG、非空裁切和全部分类数量。"""
    # 1、目录统计与真实记录一致，所有帧均有实际图像内容。
    catalog = material_catalog()
    assert catalog["summary"] == {
        "characters": 5,
        "character_frames": 528,
        "furniture": 12,
        "decor": 16,
        "effects": 8,
    }
    assert sum(entry["frame_count"] for entry in catalog["characters"]) == 528
    for entry in catalog["characters"]:
        folder = LIBRARY / "characters" / entry["id"]
        value = json.loads((folder / "avatar.json").read_text("utf-8"))
        assert value == entry["manifest"]
        for page, filename in enumerate(value["images"]):
            with Image.open(folder / filename) as image:
                assert image.mode == "RGBA" and image.getchannel("A").getextrema() == (0, 255)
                for frame in value["frame_rects"]:
                    if frame["page"] == page:
                        x, y, w, h = frame["rect"]
                        assert image.getchannel("A").crop((x, y, x + w, y + h)).getbbox()
    # 2、家具一项一帧，特效一项四帧；不能引用图集之外或空白区域。
    for kind, count in (("furniture", 12), ("decor", 16), ("effects", 8)):
        entries = [entry for entry in catalog["objects"] if entry["kind"] == kind]
        assert len(entries) == count
        for entry in entries:
            with Image.open(LIBRARY / entry["image"]) as image:
                assert len(entry["frames"]) == (4 if kind == "effects" else 1)
                assert list(image.size) == entry["atlas_size"]
                for x, y, w, h in entry["frames"]:
                    assert 0 <= x < x + w <= image.width and 0 <= y < y + h <= image.height
                    assert image.getchannel("A").crop((x, y, x + w, y + h)).getbbox()
