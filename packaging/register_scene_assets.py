"""只读登记八向场景资源；JSON 是原生几何与画布共同读取的素材合同。"""

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "desktop/src"), str(ROOT / "backend/src")]
from roomcrew_desktop.assets.library import AvatarLibrary  # noqa: E402
from roomcrew_desktop.assets.registration import head_width  # noqa: E402

DIRECTIONS = ("s", "se", "e", "ne", "n", "nw", "w", "sw")
DEFINITIONS: dict[str, dict[str, Any]] = {
    "desk": {
        "label": "电脑桌",
        "footprint": [4, 3],
        "base_direction": "se",
        "interaction": "workstation",
        "height": 94,
        "art": "workstation-v3",
    },
    "security": {
        "label": "监管台",
        "footprint": [4, 3],
        "base_direction": "se",
        "interaction": "workstation",
        "height": 94,
        "art": "workstation-v3",
    },
    "chair": {
        "label": "办公椅",
        "footprint": [2, 1],
        "base_direction": "se",
        "interaction": "chair",
        "height": 48,
    },
    "sofa": {
        "label": "双人沙发",
        "footprint": [4, 3],
        "base_direction": "sw",
        "interaction": "lounge",
        "height": 94,
    },
    "meeting": {
        "label": "会议桌",
        "footprint": [5, 6],
        "base_direction": "sw",
        "interaction": "meeting",
        "height": 114,
        "seat_layout": {"distance": 1.65, "span": 1.0},
    },
    "screen": {"label": "画布白板", "footprint": [4, 1], "base_direction": "sw", "height": 124},
    "tea_table": {"label": "茶几", "footprint": [3, 2], "base_direction": "sw", "height": 54},
    "fridge": {
        "label": "冰箱",
        "footprint": [1, 2],
        "base_direction": "se",
        "height": 80,
        "legacy": "furniture-09",
    },
    "cabinet": {
        "label": "文件柜",
        "footprint": [2, 1],
        "base_direction": "se",
        "height": 82,
        "legacy": "furniture-08",
    },
    "bookcase": {
        "label": "书架",
        "footprint": [2, 1],
        "base_direction": "se",
        "height": 134,
        "legacy": "furniture-07",
    },
    "archive": {
        "label": "档案室",
        "footprint": [2, 1],
        "base_direction": "se",
        "height": 94,
        "legacy": "furniture-08",
    },
    "coffee": {
        "label": "咖啡机",
        "footprint": [1, 1],
        "base_direction": "se",
        "height": 42,
        "legacy": "decor-09",
    },
    "plant": {
        "label": "绿植",
        "footprint": [1, 1],
        "base_direction": "se",
        "height": 66,
        "legacy": "furniture-11",
        "rotation_symmetric": True,
    },
    "lamp": {
        "label": "落地灯",
        "footprint": [1, 1],
        "base_direction": "se",
        "height": 74,
        "legacy": "decor-07",
        "rotation_symmetric": True,
    },
}


GEOMETRY_ART = {
    "desk": "workstation",
    "security": "workstation",
    "chair": "chair",
    "sofa": "sofa",
    "meeting": "meeting",
    "tea_table": "tea_table",
    "screen": "screen",
    "archive": "archive",
    "bookcase": "bookcase",
}


def opaque(value: int) -> int:
    """因为低透明边缘不能把相邻方向连在一起，需要只在测量时使用明确轮廓。"""
    # 1、只返回分析蒙版，不更改源 PNG。
    return 255 if value >= 100 else 0


def rectangles(
    path: Path, rows: int = 2, bands: tuple[int, ...] | None = None, columns: int = 4
) -> tuple[list[list[int]], list[int]]:
    """因为方向和动作图集的行列数不同，需要按明确网格读取透明轮廓并保留完整精灵。"""
    # 1、每件资源只解码一次；输出源坐标，不进行裁剪或背景编辑。
    result = []
    with Image.open(path) as picture:
        alpha = picture.getchannel("A")
        edges = bands or tuple(index * alpha.height // rows for index in range(rows + 1))
        for row in range(rows):
            for col in range(columns):
                x, y = col * alpha.width // columns, edges[row]
                region = (x, y, (col + 1) * alpha.width // columns, edges[row + 1])
                box = alpha.crop(region).point(opaque).getbbox()
                if not box:
                    raise ValueError(f"缺少方向: {path.name} {row}/{col}")
                result.append([x + box[0], y + box[1], box[2] - box[0], box[3] - box[1]])
        return result, list(picture.size)


def character(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """因为八向坐姿仍供兼容回退使用，需要只登记当前有效的地面基线和接触标记。"""
    # 1、同一角色所有方向共用头部尺度，源图保持不变。
    rects, size = rectangles(path)
    directions = list(DIRECTIONS)
    with Image.open(path) as picture:
        alpha = picture.getchannel("A")
        widths = []
        for x, y, width, height in rects:
            widths.append(head_width(alpha.crop((x, y, x + width, y + height))) or width * 0.65)
    unit = 128 / manifest["frame_size"][1]
    scale = 38 / (statistics.median(widths) * unit)
    pivot_x, pivot_y = manifest["pivot"]
    roots = {
        "s": 0.5,
        "se": 0.40,
        "e": 0.35,
        "ne": 0.35,
        "n": 0.5,
        "nw": 0.65,
        "w": 0.65,
        "sw": 0.60,
    }
    frames = []
    with Image.open(path) as picture:
        sole_alpha = picture.getchannel("A")
    for direction, rect in zip(directions, rects, strict=True):
        width, height = rect[2:]
        hip_x = width * roots[direction]
        hip_y = height * (0.78 if direction in {"n", "nw", "ne"} else 0.73)
        lower = (
            sole_alpha.crop(
                (rect[0], rect[1] + round(height * 0.90), rect[0] + width, rect[1] + height)
            )
            .point(opaque)
            .getbbox()
        )
        sole_x = (lower[0] + lower[2]) / 2 if lower else hip_x
        frames.append(
            {
                "rect": rect,
                "scale": scale,
                "offset": [pivot_x - hip_x * scale, pivot_y - height * scale],
                "direction": direction,
                "contact": {
                    "hip": [0, (hip_y - height) * scale * unit],
                    "soles": [(sole_x - hip_x) * scale * unit, 0],
                    "seat_height": (height - hip_y) * scale * unit,
                },
            }
        )
    return {
        "image": "studio/assets/" + path.parent.name + "/" + path.name,
        "size": size,
        "frames": frames,
        "name": manifest["name"],
        "virtual_size": manifest["frame_size"],
        "pivot": manifest["pivot"],
    }


def paired_character(
    path: Path, manifest: dict[str, Any], row: int, transition: bool = False
) -> dict[str, Any]:
    """因为标准椅和人物应由美术配套保证贴合，需要登记椅脚原点的完整交互帧，避免运行时拼接两个臀部。"""
    # 1、只测量原图，同一人物的动作帧共享头部尺度；图中已包含椅子，不能重复绘制空椅。
    columns = 6 if transition else 4
    all_rects, size = rectangles(path, 4, columns=columns)
    rects = all_rects[row * columns : (row + 1) * columns]
    with Image.open(path) as picture:
        alpha = picture.getchannel("A")
        widths = [head_width(alpha.crop((x, y, x + w, y + h))) or w * 0.65 for x, y, w, h in rects]
    unit = 128 / manifest["frame_size"][1]
    scale = 38 / (statistics.median(widths) * unit)
    frames = []
    standing_foot = None
    for index, rect in enumerate(rects):
        width, height = rect[2:]
        # 2、中央椅脚轮是整段固定原点，不能依据人物裁切框宽度猜位置，站起来后裁切会明显变宽。
        crop = alpha.crop((rect[0], rect[1], rect[0] + width, rect[1] + height))
        lower = crop.crop((round(width * 0.5), round(height * 0.85), width, height)).point(opaque)
        box = lower.getbbox()
        if not box:
            raise ValueError("配套椅缺少脚轮接触标记")
        edge = lower.crop((0, box[3] - 3, lower.width, box[3])).getbbox()
        root = round(width * 0.5) + (edge[0] + edge[2]) / 2
        floor = round(height * 0.85) + box[3]
        if transition and index == len(rects) - 1:
            # 3、站立鞋底在椅子左侧，单独登记鞋底与椅脚的投影差，供起坐与行走衔接。
            shoes = crop.crop((0, round(height * 0.82), round(width * 0.5), height)).point(opaque)
            shoe_box = shoes.getbbox()
            edge_box = shoes.crop((0, shoe_box[3] - 3, shoes.width, shoe_box[3])).getbbox()
            foot_x = (edge_box[0] + edge_box[2]) / 2
            foot_y = round(height * 0.82) + shoe_box[3]
            standing_foot = [(foot_x - root) * scale * unit, (foot_y - floor) * scale * unit]
        frames.append(
            {
                "rect": rect,
                "scale": scale,
                "offset": [
                    manifest["pivot"][0] - root * scale,
                    manifest["pivot"][1] - floor * scale,
                ],
                "includes_seat": True,
                "seat_style": "sage-chair-v1",
            }
        )
    # 4、东北/西南明确镜像已绘的人物交互帧，不宣称新增了独立原绘视角。
    return {
        "image": "studio/assets/" + path.parent.name + "/" + path.name,
        "size": size,
        "frames": frames,
        "standing_foot": standing_foot,
        "directions": {
            "nw": {"idle": [0], "work": [1, 2]},
            "se": {"idle": [3]},
            "ne": {"idle": [0], "work": [1, 2], "mirror": True},
            "sw": {"idle": [3], "mirror": True},
        },
    }


def calibrated_workstation() -> dict[str, Any]:
    """因为新桌子原画严格沿统一三维底稿制作，需要按作者坐标登记尺度与接触，替代猜测框内比例。"""
    # 1、保留原图像素，只测量有效轮廓；相机和来源尺寸可追溯到 scene-v2 制作底稿。
    path = ROOT / "desktop/ui/studio/assets/scene-v2/workstation-se.png"
    with Image.open(path) as picture:
        bounds = picture.getchannel("A").point(opaque).getbbox()
        size = list(picture.size)
    if not bounds or size[0] != size[1]:
        raise ValueError("统一投影桌子需要完整正方形画布")
    x, y, right, bottom = bounds
    width, height = right - x, bottom - y
    ratio = size[0] / 1024
    density = ratio * 8
    # 2、家具原点沿用旧世界锚点；座点比它前移 0.3 格，对应原画中的真正人物脚点。
    origin = (700 * ratio, 590 * ratio)
    base = (1.8, 0.65, 0)
    keyboard = (1.08, 0.85, 1.45)
    ground_x = origin[0] + density * 24 * (base[0] - base[1])
    ground_y = origin[1] + density * 12 * (base[0] + base[1])
    key_x = origin[0] + density * 24 * (keyboard[0] - keyboard[1])
    key_y = origin[1] + density * (
        12 * (keyboard[0] + keyboard[1]) - 12 * math.sqrt(6) * keyboard[2]
    )
    # 3、只覆盖已验证方向；其余旧方向不伪称已按新规范重制。
    return {
        "image": "../scene-v2/workstation-se.png",
        "atlas_size": size,
        "rect": [x, y, width, height],
        "display_height": height / density,
        "operator_ground": [(ground_x - x) / width, (ground_y - y) / height],
        "ground": [(ground_x - x) / width, (ground_y - y) / height],
        "keyboard": [(key_x - x) / width, (key_y - y) / height],
        "camera_profile_id": "rc-ortho-2to1-v1",
        "axis_error_degrees": [0.3192, 0.5062],
        "coverage": "drawn",
    }


def calibrated_furniture(kind: str) -> dict[str, dict[str, Any]]:
    """因为成品图集会改变源像素密度，需要以固定实体尺寸登记每向原点，保持等比且不逐帧追踪轮廓。

    输入为已制作家具类型；返回只读方向注册。若图集或制作底稿缺失则中止发布，不回退猜测尺度。
    """
    # 1、底稿保存真正旋转后的投影边界，成品仅测量一次；运行时不读取轮廓或重算比例。
    folder = ROOT / "desktop/ui/studio/assets/scene-v2"
    guide = json.loads((folder / "source" / f"{kind}-guide.json").read_text("utf-8"))
    rects, size = rectangles(folder / f"{kind}.png")
    result = {}
    for direction, rect in zip(DIRECTIONS, rects, strict=True):
        bounds = guide["views"][direction]["projected_bounds"]
        height = bounds[3] - bounds[1]
        density = rect[3] / height
        # 2、只允许等比缩放；绘画轮廓的宽度偏差留下审计，不用横向拉伸掩盖美术误差。
        expected_width = (bounds[2] - bounds[0]) * density
        origin = [-bounds[0] * density, -bounds[1] * density]
        result[direction] = {
            "image": f"../scene-v2/{kind}.png",
            "atlas_size": size,
            "rect": rect,
            "display_height": height,
            "ground": [origin[0] / rect[2], origin[1] / rect[3]],
            "world_origin_at_center": True,
            "camera_profile_id": guide["camera_profile_id"],
            "physical_profile": "legacy-character-seat22",
            "outline_width_ratio": rect[2] / expected_width,
            "coverage": "drawn",
            "validation": "authored-calibration-runtime-review",
        }
        # 3、椅子和沙发的座面来自同一物理点；茶几花盆有明确桌面挂点，不使用屏幕百分比猜位置。
        if kind in {"chair", "sofa"}:
            result[direction]["seat"] = [origin[0] / rect[2], (origin[1] - 22 * density) / rect[3]]
        if kind == "tea_table":
            result[direction]["plant_attachment"] = [
                origin[0] / rect[2],
                (origin[1] - 12 * math.sqrt(6) * 0.80 * density) / rect[3],
            ]
        if kind == "workstation":
            yaw = math.radians(guide["views"][direction]["yaw_degrees"])
            result[direction]["operator_ground"] = normalized_attachment(
                result[direction], (1.1, -0.75, 0), yaw
            )
            result[direction]["ground"] = result[direction]["operator_ground"]
            result[direction]["keyboard"] = normalized_attachment(
                {**result[direction], "ground": [origin[0] / rect[2], origin[1] / rect[3]]},
                (0.38, -0.55, 1.45),
                yaw,
            )
    return result


def normalized_attachment(
    view: dict[str, Any], point: tuple[float, float, float], yaw: float
) -> list[float]:
    """因为桌面组件与操作侧应随实体转向，需要将作者三维挂点转换到成品图的归一坐标。"""
    # 1、输入的 ground 是制作原点，不是屏幕裁切中心；同一高度只使用等比源密度。
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = point
    rx, ry = x * c - y * s, x * s + y * c
    density = view["rect"][3] / view["display_height"]
    return [
        view["ground"][0] + 24 * (rx - ry) * density / view["rect"][2],
        view["ground"][1] + (12 * (rx + ry) - 12 * math.sqrt(6) * z) * density / view["rect"][3],
    ]


def main() -> None:
    """因为素材需要可以被用户替换，需要输出稳定的数据目录及明确的原绘/对称/缺失覆盖，避免隐藏硬编码。"""
    # 1、所有设备先进入同一目录；未完成的原绘方向明确标为 legacy，不把复制同图当作八向原画。
    folder = ROOT / "desktop/ui/studio/assets/scene-v1"
    old = json.loads(
        (folder.parent / "library-v1/catalog.js")
        .read_text("utf-8")
        .split("=", 1)[1]
        .strip()
        .rstrip(";")
    )
    materials = {}
    geometry: dict[str, dict[str, dict[str, Any]]] = {}
    for kind, definition in DEFINITIONS.items():
        definition.setdefault("default_direction", definition["base_direction"])
        definition.setdefault("seat_height", 22)
        if kind in GEOMETRY_ART:
            art = GEOMETRY_ART[kind]
            if art not in geometry:
                geometry[art] = calibrated_furniture(art)
                if art == "workstation":
                    geometry[art]["se"].update(calibrated_workstation())
            views = geometry[art]
            materials[kind] = {
                "image": "../scene-v2/" + art + ".png",
                "atlas_size": views["s"]["atlas_size"],
                "height": definition["height"],
                "views": views,
            }
        elif kind in ("fridge", "cabinet", "coffee"):
            # 2、尚在使用的旧八向资源独立登记，不再先装旧图后用新图覆盖两遍。
            path = folder / (kind + ".png")
            rects, size = rectangles(path)
            order = ("s", "sw", "w", "nw", "n", "ne", "e", "se")
            materials[kind] = {
                "image": "../scene-v1/" + path.name,
                "atlas_size": size,
                "height": definition["height"],
                "views": {
                    direction: {
                        "rect": rect,
                        "coverage": "drawn",
                        "ground": [0.5, 1],
                        "seat": [0.5, 0.63],
                        "keyboard": [0.56, 0.45],
                    }
                    for direction, rect in zip(order, rects, strict=True)
                },
            }
        else:
            entry = next(item for item in old["objects"] if item["id"] == definition["legacy"])
            materials[kind] = {
                "image": entry["image"],
                "atlas_size": entry["atlas_size"],
                "height": definition["height"],
                "views": {
                    direction: {
                        "rect": entry["frames"][0],
                        "coverage": "symmetric"
                        if definition.get("rotation_symmetric")
                        else "legacy",
                        "ground": [0.5, 1],
                    }
                    for direction in DIRECTIONS
                },
            }
    # 3、只有内容 ID 匹配的内置角色附加新坐姿，用户原素材和帧号不变。
    library = AvatarLibrary(ROOT / ".cache/scene-art-fingerprints")
    people = {}
    for row, role in enumerate(("assistant", "employee", "guardian", "owner")):
        source = folder.parent / "library-v1/characters" / role / "avatar.json"
        asset = library.import_manifest(source)
        people[asset["id"]] = character(
            folder / f"seated-{role}.png", library.asset(asset["id"])["manifest"]
        )
        people[asset["id"]]["role"] = role
        people[asset["id"]]["paired"] = paired_character(
            folder.parent / "scene-v2/paired-chair-v2.png",
            library.asset(asset["id"])["manifest"],
            row,
        )
        people[asset["id"]]["transition"] = paired_character(
            folder.parent / "scene-v2/chair-rise-v3.png",
            library.asset(asset["id"])["manifest"],
            row,
            True,
        )
    keyboard_rects, keyboard_size = rectangles(folder / "workstation-v3.png", 3, (0, 350, 697, 887))
    value = {
        "format": "roomcrew.scene-assets",
        "version": 1,
        "directions": list(DIRECTIONS),
        "definitions": DEFINITIONS,
        "materials": materials,
        "characters": people,
        "attachments": {
            "keyboard": {
                "image": "../scene-v1/workstation-v3.png",
                "atlas_size": keyboard_size,
                "width": 38,
                "views": {
                    direction: {
                        "rect": keyboard_rects[index],
                        "coverage": "drawn",
                    }
                    for direction, index in {"nw": 9, "ne": 8, "se": 11, "sw": 10}.items()
                },
            }
        },
        "character_requirements": {
            "required": [
                "idle.standing",
                "walk.standing",
                "sit_down.standing",
                "stand_up.standing",
                "idle.seated",
                "work.seated",
                "ask.seated",
                "report.seated",
            ],
            "recommended": ["run", "phone", "game", "read", "talk", "alert"],
            "contacts": ["hip", "soles", "hands", "bubble"],
            "policy": "缺动作可复用兼容姿态；缺接触不能宣称适配；坐姿不能回退站姿",
        },
    }
    # 4、两端读取同一份 JSON，浏览器脚本只是完全相同内容的只读包装。
    content = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    (folder / "catalog.json").write_text(content, "utf-8")
    (folder / "catalog.js").write_text("window.ROOMCREW_SCENE_ASSETS=" + content + ";\n", "utf-8")
    print(
        json.dumps(
            {
                "materials": len(materials),
                "drawn_views": sum(
                    view["coverage"] == "drawn"
                    for item in materials.values()
                    for view in item["views"].values()
                ),
                "seated_views": len(people) * 8,
            }
        )
    )


if __name__ == "__main__":
    main()
