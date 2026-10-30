"""登记五套角色的通话姿态；补页只用于内置内容，不改变用户两页导入合同。"""

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop/src"))
UI = ROOT / "desktop/ui"
# 原绘五行并非等高；边界取双列透明间隙，避免上一行的鞋子进入下一帧。
CALL_ROW_EDGES = (0, 363, 726, 1092, 1452, 1774)


def call_frames(image: Image.Image, row: int, manifest: dict, reference: dict) -> list[dict]:
    """因为通话不能改变角色大小，需要按原角色头部标尺和同一页固定比例登记两张真实姿势。"""
    # 1、只读透明轮廓生成矩形，不改写 PNG 像素；背景低透明像素不作为人体几何。
    from roomcrew_desktop.assets.registration import head_width

    pieces = []
    if image.size != (887, 1774):
        raise ValueError("通话原图尺寸变化，需要重新目检并登记行边界")
    alpha = image.getchannel("A")
    for column in range(2):
        x0, x1 = round(column * image.width / 2), round((column + 1) * image.width / 2)
        y0, y1 = CALL_ROW_EDGES[row : row + 2]
        bounds = alpha.crop((x0, y0, x1, y1)).point([0] * 16 + [255] * 240).getbbox()
        if not bounds:
            raise ValueError("通话图集有空帧")
        left, top, right, bottom = bounds
        rect = [x0 + left, y0 + top, right - left, bottom - top]
        crop = alpha.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
        pieces.append((rect, head_width(crop) or rect[2] * 0.6))
    # 2、对照已有配套姿势，确保电话动作和工作姿势共用头部尺度。
    with Image.open(UI / reference["image"]) as previous:
        rect = reference["frame"]["rect"]
        mask = previous.getchannel("A").crop(
            (rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3])
        )
        target = (head_width(mask) or rect[2] * 0.6) * reference["frame"]["scale"]
    scale = target / (sum(piece[1] for piece in pieces) / len(pieces))
    scale = min(scale, (manifest["pivot"][1] - 4) / max(piece[0][3] for piece in pieces))
    frames = []
    for rect, _ in pieces:
        crop = alpha.crop((rect[0], rect[1] + rect[3] - 20, rect[0] + rect[2], rect[1] + rect[3]))
        weights = [sum(crop.crop((x, 0, x + 1, crop.height)).tobytes()) for x in range(crop.width)]
        center = sum(x * weight for x, weight in enumerate(weights)) / max(1, sum(weights))
        frames.append(
            {
                "rect": rect,
                "scale": scale,
                "offset": [
                    round(manifest["pivot"][0] - center * scale),
                    round(manifest["pivot"][1] - rect[3] * scale),
                ],
            }
        )
    return frames


def main() -> None:
    """因为 MCP 通话与摸鱼手机必须区分，需要只为明确的五套内置形象登记电话贴耳的原绘片段。"""
    # 1、内置内容 ID 保持原样，不覆盖用户已经导入的文件或动作绑定。
    path = UI / "studio/assets/scene-v1/catalog.json"
    catalog = json.loads(path.read_text("utf-8"))
    people = json.loads((UI / "studio/assets/library-v1/catalog.json").read_text("utf-8"))[
        "characters"
    ]
    phone_path = UI / "studio/assets/scene-v2/telephone-calls.png"
    with Image.open(phone_path) as image:
        for row, role in enumerate(("assistant", "employee", "guardian", "owner", "hippo")):
            item = next(person for person in people if person["id"] == role)
            metadata_path = UI / "studio/assets/library-v1/characters/hippo/display.json"
            entry = (
                json.loads(metadata_path.read_text("utf-8"))
                if role == "hippo"
                else catalog["characters"][item["registered_id"]]
            )
            if role == "hippo":
                reference = {
                    "image": "studio/assets/library-v1/characters/hippo/work.png",
                    "frame": item["manifest"]["frame_rects"][28],
                }
            else:
                reference = {
                    "image": entry["paired"]["image"],
                    "frame": entry["paired"]["frames"][3],
                }
            entry["call"] = {
                "image": "studio/assets/scene-v2/telephone-calls.png",
                "size": list(image.size),
                "frames": call_frames(image, row, item["manifest"], reference),
            }
            if role == "hippo":
                metadata_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), "utf-8")
                metadata_path.with_suffix(".js").write_text(
                    "/* 内置吉祥物与通话显示登记。 */\nwindow.ROOMCREW_MASCOT="
                    + json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
                    + ";\nwindow.ROOMCREW_SCENE_ASSETS.characters[window.ROOMCREW_MASCOT.id]="
                    + "window.ROOMCREW_MASCOT;\n",
                    "utf-8",
                )
    # 2、同步可检查 JSON 与纯本地脚本，运行时不扫描磁盘或加载任意路径。
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8")
    path.with_suffix(".js").write_text(
        "/* 内置场景资源。 */\nwindow.ROOMCREW_SCENE_ASSETS="
        + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        "utf-8",
    )


if __name__ == "__main__":
    main()
