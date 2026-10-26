"""登记四套完整角色与环境素材，生成正式清单及可浏览素材总览的数据。"""

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

from asset_layout import grid_regions, object_regions
from register_portrait_atlas import clip

sys.path[:0] = [
    str(Path(__file__).resolve().parents[3] / "backend/src"),
    str(Path(__file__).resolve().parents[3] / "desktop/src"),
]

from roomcrew.assets.library import AvatarLibrary
from roomcrew.assets.schema import validate_manifest
from roomcrew.contracts.animation import GESTURES

ROOT = Path(__file__).resolve().parents[3]
LIBRARY = ROOT / "desktop/ui/studio/assets/library-v1"
ROLES = {
    "owner": "阿晨 · 成员",
    "assistant": "小禾 · 助手",
    "employee": "小岚 · 员工",
    "guardian": "守望 · 监管员",
}


def core_clips(role: str) -> list[dict[str, Any]]:
    """因为各生成页的实际行数不同，需要按检查后的内容登记，不虚报不存在的姿态帧。"""
    # 1、四套素材都有真实正背步态和坐姿手机；不同数量的闲置帧按实际内容选择。
    short = role in {"owner", "guardian"}
    tail = 48 if short else 56
    front_idle = {
        "owner": [40, 43],
        "guardian": [46],
        "employee": [40, 42, 44],
        "assistant": [48, 49, 50, 51],
    }[role]
    back_idle = [44, 45, 47] if short else [52, 53, 54, 55]
    phone = {
        "owner": [41, 42],
        "employee": [41, 43, 45, 46, 47],
        "guardian": [40, 41, 42, 43],
        "assistant": list(range(40, 48)),
    }[role]
    return [
        clip("walk", list(range(8)), 10),
        clip("run", list(range(8, 16)), 14),
        clip("walk", list(range(16, 24)), 10, "ne"),
        clip("run", list(range(24, 32)), 14, "ne"),
        clip("phone", list(range(32, 40)), 6, posture="seated"),
        clip("phone", phone, 4),
        clip("idle", front_idle, 2),
        clip("idle", back_idle, 2, "ne"),
        clip("idle", [tail, tail + 1], 2, posture="seated"),
        clip("idle", [tail + 2, tail + 3], 2, "ne", "seated"),
        clip("sit", [tail, tail + 1], 2, posture="seated"),
        clip("sit_down", [front_idle[0], tail + 4, tail + 5, tail], 10, loop=False),
        clip("stand_up", [tail, tail + 5, tail + 4, front_idle[0]], 10, loop=False),
    ]


def work_clips(offset: int) -> list[dict[str, Any]]:
    """因为当前全部动作都要有对应美术，需要把工作页按真实道具和姿态映射到有限语义。"""
    # 1、每组四帧对应一种实际画面，工作与打字明确复用，其他动作不能拿手机代替。
    specs = [
        ("think", 0, "standing"),
        ("read", 4, "standing"),
        ("read", 8, "seated"),
        ("type", 12, "seated"),
        ("write", 16, "seated"),
        ("type", 20, "standing"),
        ("write", 24, "standing"),
        ("talk", 28, "standing"),
        ("ask", 32, "standing"),
        ("report", 36, "standing"),
        ("alert", 40, "standing"),
        ("listen", 44, "standing"),
        ("game", 48, "seated"),
        ("water", 52, "standing"),
        ("relax", 56, "standing"),
    ]
    result = [
        clip(action, list(range(offset + start, offset + start + 4)), 5, posture=posture)
        for action, start, posture in specs
    ]
    for item in list(result):
        if item["action"] == "type":
            result.append({**item, "action": "work"})
    # 2、四种额外表情使用实际绘制的闲置姿态；不宣称每个动作都有五种表情。
    for index, expression in enumerate(("focused", "curious", "concerned", "smile")):
        result.append({**clip("idle", [offset + 60 + index], 1), "expression": expression})
    return result


def register_character(role: str) -> dict[str, Any]:
    """因为完整角色包含基础页与工作页，需要校准两页尺度后登记可正式导入的多页清单。"""
    # 1、只读原始 PNG，校准体型采用受约束的绘制缩放元数据，不修改像素。
    folder = LIBRARY / "characters" / role
    core, core_size = grid_regions(
        folder / "core.png", 7 if role in {"owner", "guardian"} else 8, 8, trim_fragments=True
    )
    work, work_size = grid_regions(folder / "work.png", 8, 8, trim_fragments=True)
    # 2、三张员工游戏帧与上一行鞋尖有细像素相连，按原图核查后的头顶边界登记裁切。
    if role == "employee":
        for index in (49, 50, 51):
            rect = work[index]["rect"]
            if rect[1] < 986:
                rect[3] -= 986 - rect[1]
                rect[1] = 986
    base = core_clips(role)
    idle = next(item for item in base if item["action"] == "idle" and item["direction"] == "se")
    core_height = statistics.median(core[index]["rect"][3] for index in idle["frames"])
    work_height = statistics.median(
        work[index]["rect"][3] for index in [*range(8), *range(20, 48), *range(56, 64)]
    )
    scales = [1.0, round(core_height / work_height, 4)]
    figures = []
    for page, frames in enumerate((core, work)):
        for frame in frames:
            scale = scales[page]
            flight = (
                (0, 3, 6, 2, 0, 3, 6, 2)[frame["column"]]
                if page == 0 and frame["row"] in {1, 3}
                else 0
            )
            figures.append({**frame, "page": page, "scale": scale, "flight": flight})
    half = math.ceil(
        max(max(f["root"] * f["scale"], (f["rect"][2] - f["root"]) * f["scale"]) for f in figures)
        + 6
    )
    height = math.ceil((max(f["rect"][3] * f["scale"] + f["flight"] for f in figures) + 8) / 8) * 8
    width, baseline = half * 2, height - 4
    rectangles = [
        {
            "page": f["page"],
            "scale": f["scale"],
            "rect": f["rect"],
            "offset": [
                round(half - f["root"] * f["scale"]),
                baseline - math.ceil(f["rect"][3] * f["scale"]) - f["flight"],
            ],
        }
        for f in figures
    ]
    # 3、当前 20 种语义全部覆盖，姿态与方向缺口仍由总览诚实列出。
    clips = [*base, *work_clips(len(core))]
    if {item["action"] for item in clips} != GESTURES:
        raise ValueError("角色动作语义不完整")
    manifest = {
        "format": "roomcrew.avatar",
        "version": 3,
        "name": ROLES[role],
        "images": ["core.png", "work.png"],
        "frame_size": [width, height],
        "pivot": [half, baseline],
        "mirror_west": True,
        "pixel_art": False,
        "frame_rects": rectangles,
        "clips": clips,
    }
    validate_manifest(manifest, [core_size, work_size])
    (folder / "avatar.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    registration = AvatarLibrary(ROOT / ".cache/full-material-verification").import_manifest(
        folder / "avatar.json"
    )
    return {
        "id": role,
        "name": ROLES[role],
        "kind": "character",
        "manifest": manifest,
        "images": [f"characters/{role}/core.png", f"characters/{role}/work.png"],
        "registered_id": registration["id"],
        "frame_count": len(figures),
        "action_count": len(GESTURES),
        "edge_frames": [i for i, f in enumerate(figures) if f["edge"]],
        "notes": "20 种动作均有对应片段；非所有方向、表情、姿态组合均已独立绘制。",
    }


def register_objects() -> list[dict[str, Any]]:
    """因为完整素材库还包含家具、装饰和状态特效，需要登记真实裁切区域及各自接入状态。"""
    # 1、静态素材一物一项，特效一行四帧，全部只引用已制作的本地图集。
    furniture = [
        "接待台",
        "员工桌",
        "会议桌",
        "办公椅",
        "双人沙发",
        "茶几",
        "书架",
        "文件柜",
        "冰箱",
        "会议大屏",
        "龟背竹",
        "小盆栽",
    ]
    decor = [
        "百叶窗",
        "玻璃门",
        "地毯",
        "吊灯",
        "挂钟",
        "便签板",
        "落地灯",
        "衣帽架",
        "咖啡机",
        "饮水机",
        "打印机",
        "笔记本电脑",
        "书籍资料",
        "咖啡杯",
        "台灯",
        "抽屉柜",
    ]
    effects = ["思考", "疑问", "提醒", "汇报", "核验通过", "暂停", "协作", "安全服务"]
    result = []
    for category, rows, names in (
        ("furniture", 3, furniture),
        ("decor", 4, decor),
        ("effects", 8, effects),
    ):
        source = LIBRARY / "objects" / f"{category}.png"
        regions, size = (
            grid_regions(source, rows, 4, 0.4)
            if category == "effects"
            else object_regions(source, rows, 4)
        )
        for index, name in enumerate(names):
            frames = (
                regions[index * 4 : index * 4 + 4] if category == "effects" else [regions[index]]
            )
            result.append(
                {
                    "id": f"{category}-{index + 1:02d}",
                    "name": name,
                    "kind": category,
                    "image": f"objects/{category}.png",
                    "atlas_size": list(size),
                    "frames": [frame["rect"] for frame in frames],
                    "fps": 5,
                    "integration": environment_integration(category, index + 1),
                }
            )
    return result


def environment_integration(category: str, number: int) -> str:
    """因为总览必须区分制作完成与实际接入，需要按固定环境映射说明每项用途。"""
    # 1、映射与环境渲染器对应，未接入项保持明确说明。
    if category == "furniture" and number in {1, 2, 3, 5, 6, 7, 8, 9, 10, 11}:
        return "已接入房间对应家具；碰撞、锚点与人工点击沿用场景合同"
    if category == "furniture" and number == 12:
        return "已用于视口植物前景；不作为交互家具或导航障碍"
    if category == "decor" and number in {7, 9}:
        return "已接入房间落地灯/咖啡机家具类型，可在布置模式添加"
    return "素材已制作，可总览预览；此原图尚未接入对应房间表现"


def main() -> None:
    """因为用户需要可核查的完整素材库，需要生成真实清单、覆盖统计与本地浏览数据。"""
    # 1、人物导入走生产验证器，不用假注册 ID 填充总览。
    characters = [register_character(role) for role in ROLES]
    objects = register_objects()
    catalog = {
        "version": 1,
        "characters": characters,
        "objects": objects,
        "summary": {
            "characters": len(characters),
            "character_frames": sum(c["frame_count"] for c in characters),
            "furniture": 12,
            "decor": 16,
            "effects": 8,
        },
    }
    (LIBRARY / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8"
    )
    (LIBRARY / "catalog.js").write_text(
        "window.ROOMCREW_MATERIAL_LIBRARY = " + json.dumps(catalog, ensure_ascii=False) + ";\n",
        "utf-8",
    )
    print(json.dumps(catalog["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
