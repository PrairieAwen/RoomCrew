"""只读分析新手绘图集，生成源裁切与已知内置角色的显示补充注册，不重绘像素。"""

import json
import statistics
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "desktop/src"), str(ROOT / "backend/src")]
from roomcrew_desktop.assets.library import AvatarLibrary  # noqa: E402
from roomcrew_desktop.assets.registration import head_width  # noqa: E402


def spans(mask: Image.Image, horizontal: bool) -> list[tuple[int, int]]:
    """因为生成图集不是严格等格，需要按透明留白识别完整轮廓，避免切断头发或鞋子。"""
    # 1、阈值只用于测量；返回源坐标，不修改透明度或颜色。
    size = mask.width if horizontal else mask.height
    result, start = [], None
    for index in range(size):
        region = (
            (index, 0, index + 1, mask.height) if horizontal else (0, index, mask.width, index + 1)
        )
        active = mask.crop(region).getbbox() is not None
        if active and start is None:
            start = index
        elif not active and start is not None:
            if index - start > 10:
                result.append((start, index))
            start = None
    if start is not None and size - start > 10:
        result.append((start, size))
    return result


def guardian_frames(path: Path, manifest: dict) -> tuple[list[dict], list[int]]:
    """因为监管员需要直立且稳定的坐姿，需要为新版六帧使用同一头宽尺度和固定身体中心。

    只读取透明轮廓生成显示注册，不重绘、拉伸或覆盖用户图集。
    """
    # 1、三列两行按源图分区，所有裁切均保留完整头发和鞋子。
    with Image.open(path) as picture:
        alpha = picture.getchannel("A")
        regions = []
        heads = []
        for row in range(2):
            for column in range(3):
                left, top = column * alpha.width // 3, row * alpha.height // 2
                region = (left, top, (column + 1) * alpha.width // 3, (row + 1) * alpha.height // 2)
                bounds = alpha.crop(region).point(threshold).getbbox()
                if not bounds:
                    raise ValueError("监管员姿势为空")
                rect = [
                    left + bounds[0],
                    top + bounds[1],
                    bounds[2] - bounds[0],
                    bounds[3] - bounds[1],
                ]
                regions.append(rect)
                crop = alpha.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
                head = head_width(crop)
                if head is None:
                    raise ValueError("监管员头部尺度不可测量")
                heads.append(head)
        # 2、后背四帧共享缩放和身体轴，手臂变化不能改变头宽或让人物左右晃动。
        unit = manifest.get("display_height", 128) / manifest["frame_size"][1]
        scale = 38 / (statistics.median(heads) * unit)
        pivot_x, pivot_y = manifest["pivot"]
        frames = []
        for index, rect in enumerate(regions):
            width, height = rect[2:]
            root = width * (0.40 if index < 5 else 0.48)
            frames.append(
                {
                    "rect": rect,
                    "scale": scale,
                    "offset": [pivot_x - root * scale, pivot_y - height * scale],
                }
            )
        return frames, list(picture.size)


def desk_materials(path: Path) -> list[dict]:
    """因为普通工位和监管台不能各用一套歪斜透视，需要从同视角源图注册相同尺度和座点。"""
    # 1、保留源图像素，两件桌子使用相同操作侧、膝部位置和落地线。
    result = []
    with Image.open(path) as picture:
        alpha = picture.getchannel("A")
        for column, name in enumerate(("desk", "security")):
            left = column * alpha.width // 2
            region = (left, 0, (column + 1) * alpha.width // 2, alpha.height)
            bounds = alpha.crop(region).point(threshold).getbbox()
            if not bounds:
                raise ValueError("工位素材为空")
            result.append(
                {
                    "id": "office-" + name,
                    "image": "../office-v1/desks-v2.png",
                    "atlas_size": list(picture.size),
                    "frames": [
                        [left + bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]]
                    ],
                    "contact": {"width": 112, "seat": [0.74, 0.94], "direction": "nw"},
                }
            )
    return result


def main() -> None:
    """因为内置补帧需匹配旧用户保存的内容 ID，需要用正式导入器计算指纹并生成独立显示目录。"""
    # 1、原有两页素材与用户清单不改，新增图片只由应用资源目录加载。
    folder = ROOT / "desktop/ui/studio/assets/office-v1"
    library = AvatarLibrary(ROOT / ".cache/office-art-fingerprints")
    roles = ("assistant", "employee", "guardian", "owner")
    ids, characters = {}, {}
    with Image.open(folder / "actions.png") as picture:
        alpha = picture.getchannel("A")
        mask = alpha.point(threshold)
        columns = spans(mask, True)
        if len(columns) != 8:
            raise ValueError("补充动作必须恰好八列")
        rows_by_column = []
        # 生成图最后两列的轮廓相接，舍弃；起坐仍复用原素材的站姿与新背向坐姿。
        columns = columns[:6]
        for left, right in columns:
            column_mask = mask.crop((left, 0, right, mask.height))
            rows = spans(column_mask, False)
            if len(rows) != 4:
                raise ValueError("有效动作行需要完整透明分隔")
            rows_by_column.append(rows)
        for row, role in enumerate(roles):
            source = ROOT / "desktop/ui/studio/assets/library-v1/characters" / role / "avatar.json"
            ids[library.import_manifest(source)["id"]] = role
            manifest = json.loads(source.read_text("utf-8"))
            unit = 128 / manifest["frame_size"][1]
            pivot_x, pivot_y = manifest["pivot"]
            frames = []
            for column, ((left, right), rows) in enumerate(
                zip(columns, rows_by_column, strict=True)
            ):
                top, bottom = rows[row]
                bounds = mask.crop((left, top, right, bottom)).getbbox()
                if not bounds:
                    raise ValueError("人物轮廓为空")
                top, bottom = top + bounds[1], top + bounds[3]
                rect = [
                    max(0, left - 2),
                    max(0, top - 2),
                    min(alpha.width, right + 2),
                    min(alpha.height, bottom + 2),
                ]
                crop = alpha.crop(rect)
                head = head_width(crop)
                if head is None:
                    raise ValueError("头部轮廓测量失败")
                scale = 38 / (head * unit)
                width, height = crop.size
                root_x = width * (0.40 if column < 5 else 0.48)
                frames.append(
                    {
                        "rect": [rect[0], rect[1], width, height],
                        "scale": scale,
                        "offset": [pivot_x - root_x * scale, pivot_y - height * scale],
                    }
                )
            characters[role] = frames
        size = list(picture.size)
    # 2、家具测量同样保持原图，显式裁切的静态图不增加用户图集页数上限。
    with Image.open(folder / "fixtures.png") as picture:
        alpha = picture.getchannel("A")
        materials = []
        for name, region in (
            ("chair-back", (0, 0, 627, 627)),
            ("archive", (0, 627, 680, 1254)),
            ("chair-side", (680, 627, 1254, 1254)),
        ):
            bbox = alpha.crop(region).point(threshold).getbbox()
            if not bbox:
                raise ValueError("家具轮廓为空")
            x, y = region[0] + bbox[0], region[1] + bbox[1]
            materials.append(
                {
                    "id": "office-" + name,
                    "image": "../office-v1/fixtures.png",
                    "atlas_size": list(picture.size),
                    "frames": [[x, y, bbox[2] - bbox[0], bbox[3] - bbox[1]]],
                }
            )
    # 3、新版监管员替换显示补充页，仍只给已知内置 ID 增加一页，不修改导入合同。
    guardian_manifest = json.loads(
        (ROOT / "desktop/ui/studio/assets/library-v1/characters/guardian/avatar.json").read_text(
            "utf-8"
        )
    )
    characters["guardian"], guardian_size = guardian_frames(
        folder / "guardian-v2.png", guardian_manifest
    )
    materials.extend(desk_materials(folder / "desks-v2.png"))
    value = {
        "version": 1,
        "ids": ids,
        "size": size,
        "characters": characters,
        "objects": materials,
        "character_images": {
            "guardian": {"path": "studio/assets/office-v1/guardian-v2.png", "size": guardian_size}
        },
    }
    (folder / "catalog.js").write_text(
        "/* 内置手绘补帧注册；只在显示层使用。 */\nwindow.ROOMCREW_OFFICE_ART="
        + json.dumps(value, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "roles": len(ids),
                "frames": sum(map(len, characters.values())),
                "objects": len(materials),
            }
        )
    )


def threshold(value: int) -> int:
    """因为低透明边缘不应把两个精灵误合并，需要只用清晰轮廓测量坐标。"""
    # 1、只生成分析蒙版，不写回图片。
    return 255 if value >= 100 else 0


if __name__ == "__main__":
    main()
