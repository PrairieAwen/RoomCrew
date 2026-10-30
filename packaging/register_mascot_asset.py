"""登记已由 imagegen 制作的吉祥物图集；只写裁切元数据，不修改源 PNG 像素。"""

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop/src"))

FOLDER = ROOT / "desktop/ui/studio/assets/library-v1/characters/hippo"


def rectangles(filename: str, columns: int, rows: int, scale: float, page: int) -> list[dict]:
    """因为透明画布和生成尺寸并不保证整除，需要按真实单元边界登记固定尺度与根点。

    输入为已落地的原始图集；返回可校验的矩形和偏移，不剪裁或重绘任何图像。
    """
    # 1、透明度阈值仅用于几何测量，低透明边缘仍保留在原图中。
    with Image.open(FOLDER / filename) as image:
        alpha = image.getchannel("A")
        frames = []
        for row in range(rows):
            for column in range(columns):
                x0, y0 = round(column * image.width / columns), round(row * image.height / rows)
                x1, y1 = (
                    round((column + 1) * image.width / columns),
                    round((row + 1) * image.height / rows),
                )
                cell = alpha.crop((x0, y0, x1, y1))
                bounds = cell.point([0] * 16 + [255] * 240).getbbox()
                if bounds is None:
                    raise ValueError("吉祥物图集包含空帧")
                left, top, right, bottom = bounds
                # 2、站姿以脚底中心、配套椅以轮脚中心登记，尺度在同一页所有帧保持不变。
                support = cell.crop((left, max(top, bottom - 24), right, bottom))
                sums = [
                    sum(support.crop((index, 0, index + 1, support.height)).tobytes())
                    for index in range(support.width)
                ]
                center = left + sum(index * weight for index, weight in enumerate(sums)) / max(
                    1, sum(sums)
                )
                offset = [
                    round(128 + (left - center) * scale),
                    round(244 + (top - bottom) * scale),
                ]
                frames.append(
                    {
                        "page": page,
                        "scale": scale,
                        "rect": [x0 + left, y0 + top, right - left, bottom - top],
                        "offset": offset,
                    }
                )
        return frames


def clip(
    action: str,
    frames: list[int],
    direction: str = "se",
    posture: str = "standing",
    fps: int = 6,
    loop: bool = True,
) -> dict:
    """因为图库和真实场景必须使用同一动作定义，需要集中生成有限变体并避免帧索引散落。"""
    # 1、所有引用均来自本次登记的真实姿态；复用动作在素材说明中单独标明。
    return {
        "action": action,
        "direction": direction,
        "posture": posture,
        "expression": "neutral",
        "frames": frames,
        "fps": fps,
        "loop": loop,
    }


def main() -> None:
    """因为用户需要在素材套装中直接选择新角色，需要生成正式导入清单和隔离图库目录。"""
    # 1、两页保持现有导入合同，配套起坐仅作为可信显示补页，不扩张用户导入权限。
    from roomcrew_desktop.assets.library import AvatarLibrary
    frames = rectangles("core.png", 4, 4, 0.40, 0) + rectangles("work.png", 4, 4, 0.53, 1)
    clips = [
        clip("idle", [12]),
        clip("talk", [15, 13]),
        clip("ask", [14]),
        clip("report", [13]),
        clip("think", [14]),
        clip("listen", [12]),
    ]
    for direction, start in (("se", 0), ("nw", 4), ("e", 8)):
        clips.append(clip("walk", list(range(start, start + 4)), direction, fps=8))
    for action in ("idle", "sit", "think", "listen"):
        clips.append(clip(action, [20, 21, 22, 23], "nw", "seated", 3))
        clips.append(clip(action, [28], "se", "seated", 2))
    for action in ("type", "work", "game", "write"):
        clips.append(clip(action, [16, 17, 18, 19], "nw", "seated", 6))
    clips.extend(
        [
            clip("phone", [24, 25, 26, 27], "se", "seated", 4),
            clip("ask", [29], "se", "seated"),
            clip("report", [30], "se", "seated"),
            clip("talk", [28, 30], "se", "seated", 3),
            clip("read", [31], "se", "seated"),
        ]
    )
    manifest = {
        "format": "roomcrew.avatar",
        "version": 3,
        "name": "小橘 · 男性吉祥物",
        "images": ["core.png", "work.png"],
        "frame_size": [256, 256],
        "pivot": [128, 244],
        "mirror_west": True,
        "pixel_art": False,
        "frame_rects": frames,
        "clips": clips,
    }
    (FOLDER / "avatar.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    library = AvatarLibrary(ROOT / ".cache/mascot-registration")
    imported = library.import_manifest(FOLDER / "avatar.json")
    # 2、图库覆盖按实际变体计算，不能把关键帧宣称为完整八向或独立跑步素材。
    catalog_path = FOLDER.parents[1] / "catalog.json"
    catalog = json.loads(catalog_path.read_text("utf-8"))
    catalog["characters"] = [entry for entry in catalog["characters"] if entry["id"] != "hippo"]
    catalog["characters"].append(
        {
            "id": "hippo",
            "name": manifest["name"],
            "kind": "character",
            "manifest": manifest,
            "images": ["characters/hippo/core.png", "characters/hippo/work.png"],
            "registered_id": imported["id"],
            "frame_count": len(frames),
            "action_count": len({item["action"] for item in clips}),
            "edge_frames": [],
            "coverage_level": "keyframe-preview",
            "notes": (
                "男性黄色河马吉祥物。32 个原绘关键姿态，三向行走、背向电脑操作、手机与询问；"
                "工作/书写/游戏复用打字，西向显式镜像。"
                "独立跑步、沙发配套和完整八向待补，不标记 verified。"
            ),
        }
    )
    catalog["summary"]["characters"] = len(catalog["characters"])
    catalog["summary"]["character_frames"] = sum(
        item["frame_count"] for item in catalog["characters"]
    )
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8")
    (catalog_path.with_suffix(".js")).write_text(
        "/* 随应用分发的纯素材目录。 */\nwindow.ROOMCREW_MATERIAL_LIBRARY="
        + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        "utf-8",
    )
    # 3、补充配套椅交互与固定注册信息，内容 ID 不匹配的用户素材不受影响。
    rise = rectangles("rise.png", 3, 2, 0.33, 2)
    with Image.open(FOLDER / "rise.png") as picture:
        rise_size = list(picture.size)
    metadata = {
        "id": imported["id"],
        "paired": True,
        "transition": {
            "image": "studio/assets/library-v1/characters/hippo/rise.png",
            "size": rise_size,
            "standing_foot": [-27, -6],
            "frames": rise,
        },
        "frames": frames,
        "coverage": "keyframe-preview",
        "contact_status": "estimated",
    }
    (FOLDER / "display.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8"
    )
    (FOLDER / "display.js").write_text(
        "/* 固定来源素材显示登记，不进入 Agent 执行。 */\nwindow.ROOMCREW_MASCOT="
        + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        + ";\nwindow.ROOMCREW_SCENE_ASSETS.characters[window.ROOMCREW_MASCOT.id]="
        + "window.ROOMCREW_MASCOT;\n",
        "utf-8",
    )
    print(imported["id"])


if __name__ == "__main__":
    main()
