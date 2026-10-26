"""为原始生成图集登记裁切与脚底元数据，不重画、重采样或修改 PNG 像素。"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image

sys.path[:0] = [
    str(Path(__file__).resolve().parents[3] / "backend/src"),
    str(Path(__file__).resolve().parents[3] / "desktop/src"),
]

from roomcrew.assets.library import AvatarLibrary
from roomcrew.assets.schema import validate_manifest


def inspect_frames(source: Path) -> list[dict[str, list[int]]]:
    """因为手绘各帧的透明留白并不相等，需要分析原图 alpha 生成裁切区域和统一脚底偏移。"""
    # 1、只读 alpha；原始 PNG 不被裁切、修图、变形或重新编码。
    result = []
    with Image.open(source) as picture:
        if picture.format != "PNG" or picture.mode != "RGBA" or max(picture.size) > 2048:
            raise ValueError("需要不超过 2048 像素、具有透明通道的 PNG")
        alpha = picture.getchannel("A")
        all_bounds = figure_bounds(alpha)
        for row in range(8):
            figures = [
                item for item in all_bounds if int((item[1] + item[3]) * 4 / picture.height) == row
            ]
            if len(figures) != 8:
                raise ValueError(f"第 {row + 1} 行没有识别到八个完整人物")
            for col, bounds in enumerate(sorted(figures, key=left_coordinate)):
                left, top, right, bottom = bounds
                left, top = max(0, left - 2), max(0, top - 2)
                right, bottom = min(picture.width, right + 2), min(picture.height, bottom + 2)
                # 2、以鞋底区域中心与最低不透明像素对齐，避免留白差异导致漂移。
                foot = (
                    alpha.crop((left, max(top, bottom - 9), right, bottom))
                    .point([0] * 16 + [255] * 240)
                    .getbbox()
                )
                if foot is None:
                    raise ValueError("脚底区域为空")
                foot_x = left + (foot[0] + foot[2]) / 2
                width, height = right - left, bottom - top
                offset_x = round(96 - (foot_x - left))
                flight = (0, 3, 6, 2, 0, 3, 6, 2)[col] if row in {1, 3} else 0
                offset_y = 164 - height - flight
                result.append({"rect": [left, top, width, height], "offset": [offset_x, offset_y]})
    return result


def figure_bounds(alpha: Image.Image) -> list[list[int]]:
    """因为生成图的格子并非数学等分，需要从 alpha 连通区域定位完整人物，避免截断鞋底。"""
    # 1、低透明度噪声不参与定位；只分析遮罩，不修改或输出新的像素图像。
    width, height = alpha.size
    pixels = bytearray(alpha.point([0] * 16 + [1] * 240).tobytes())
    result = []
    for seed in range(len(pixels)):
        if not pixels[seed]:
            continue
        pixels[seed] = 0
        stack, area = [seed], 0
        left, top, right, bottom = width, height, 0, 0
        while stack:
            index = stack.pop()
            y, x = divmod(index, width)
            area += 1
            left, top = min(left, x), min(top, y)
            right, bottom = max(right, x + 1), max(bottom, y + 1)
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if pixels[neighbor]:
                        pixels[neighbor] = 0
                        stack.append(neighbor)
        # 2、只接收足够大的人物区域；异常数量由上层终止，不悄悄生成错误动画。
        if area > 500:
            result.append([left, top, right, bottom])
    return result


def left_coordinate(bounds: list[int]) -> int:
    """因为每行姿态顺序由图集作者定义，需要按左边界排序保持动作帧先后。"""
    # 1、只用于已识别人物区域的稳定排序。
    return bounds[0]


def clip(
    action: str,
    frames: list[int],
    fps: int,
    direction: str = "se",
    posture: str = "standing",
    loop: bool = True,
) -> dict[str, Any]:
    """因为同一组手绘帧需要通过稳定语义接入播放器，需要统一建立纯数据动作描述。"""
    # 1、动作定义不包含业务结果或可执行事件，表情徽记仍由真实轨迹决定。
    return {
        "action": action,
        "frames": frames,
        "fps": fps,
        "direction": direction,
        "posture": posture,
        "expression": "neutral",
        "loop": loop,
    }


def build_manifest(rectangles: list[dict[str, list[int]]]) -> dict[str, Any]:
    """因为样板只验证核心美术动作，需要精确声明已有片段，不拿手机帧冒充读写工具。"""
    # 1、独立的正背面步态与手机动作；闲置帧保留低频眨眼节奏。
    idle = [48] * 12 + [49] * 3 + [50] + [48] * 9 + [51]
    phone = [40, 40, 41, 41, 42, 43, 44, 45, 46, 46, 47, 47, 46, 46, 45, 45]
    seated_phone = [32, 32, 33, 33, 34, 34, 35, 35, 36, 36, 37, 37, 38, 39, 39, 39]
    clips = [
        clip("idle", idle, 8),
        clip("idle", [52, 53, 54, 55], 2, "ne"),
        clip("walk", list(range(8)), 10),
        clip("run", list(range(8, 16)), 14),
        clip("walk", list(range(16, 24)), 10, "ne"),
        clip("run", list(range(24, 32)), 14, "ne"),
        clip("phone", phone, 8),
        clip("phone", seated_phone, 8, posture="seated"),
        clip("idle", [56] * 24 + [57], 8, posture="seated"),
        clip("idle", [58, 59], 2, "ne", "seated"),
        clip("sit", [56, 57], 2, posture="seated"),
        clip("sit_down", [48, 60, 61, 56], 10, loop=False),
        clip("stand_up", [56, 61, 60, 48], 10, loop=False),
        clip("ask", [62, 62, 62, 63], 4),
    ]
    # 2、原图始终不变；可见裁切与对齐全部来自有界元数据。
    return {
        "format": "roomcrew.avatar",
        "version": 2,
        "name": "小禾 · 手绘动画样板",
        "image": "atlas.png",
        "frame_size": [192, 168],
        "pivot": [96, 164],
        "pixel_art": False,
        "mirror_west": True,
        "frame_rects": rectangles,
        "clips": clips,
    }


def main() -> None:
    """因为生成素材要成为可分发的项目资源，需要复制原图、登记元数据并通过正式导入器复验。"""
    # 1、来源由开发者明确指定，输出固定在项目内，不覆盖已有素材。
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    source = parser.parse_args().source.resolve(strict=True)
    root = Path(__file__).resolve().parents[3]
    target = root / "desktop/ui/studio/assets/atelier-v1"
    if target.exists():
        raise ValueError("目标已存在，请先明确处理旧版本，不能自动覆盖")
    manifest = build_manifest(inspect_frames(source))
    with Image.open(source) as picture:
        validate_manifest(manifest, picture.size)
    target.mkdir(parents=True)
    shutil.copyfile(source, target / "atlas.png")
    (target / "avatar.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    # 2、经过实际 PNG 完整性、边界和 hash 注册；校验结果不进入用户正式数据。
    result = AvatarLibrary(root / ".cache/portrait-registration").import_manifest(
        target / "avatar.json"
    )
    print(
        json.dumps(
            {
                "frames": len(manifest["frame_rects"]),
                "clips": len(manifest["clips"]),
                "validated": result["id"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
