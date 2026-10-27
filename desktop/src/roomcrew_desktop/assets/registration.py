"""只读分析透明人物帧，生成统一头部尺度和脚底基线的显示元数据。"""

import io
import statistics
from typing import Any

from PIL import Image


def head_width(mask: Image.Image) -> float | None:
    """因为站坐与道具会改变整体包围框，需要用上部连续轮廓估计头宽而非拉伸整张人物。

    只分析透明度，不修改图片；无法可靠判断的矩形素材返回 None，保留原注册。
    """
    # 1、扫描头部常见高度范围，独立手指或道具不会被合并为整行宽度。
    width, height = mask.size
    pixels = mask.tobytes()
    widths = []
    for y in range(max(0, round(height * 0.08)), max(1, round(height * 0.40))):
        longest = run = 0
        for pixel in pixels[y * width : (y + 1) * width]:
            run = run + 1 if pixel >= 128 else 0
            longest = max(longest, run)
        if longest >= 8:
            widths.append(longest)
    if len(widths) < 4:
        return None
    estimate = statistics.median(sorted(widths)[-max(4, len(widths) // 3) :])
    # 2、不自动矫正不透明矩形或极窄片段；特殊素材可在人物设置关闭自动校准。
    if estimate < width * 0.25 or min(pixels) >= 128:
        return None
    return float(estimate)


def register_frames(manifest: dict[str, Any], pages: list[bytes]) -> dict[str, Any] | None:
    """因为旧导入图集也需要改善动作比例，需要在读取素材时生成可缓存的独立注册信息。

    不改变内容 hash、原清单或用户帧号；仅处理有界裁切协议，返回纯显示几何。
    """
    # 1、每页只解码一次；该方法由素材工作线程调用，不进入 Agent 执行或逐帧渲染。
    if manifest["version"] < 2 or not 1 <= len(manifest.get("frame_rects", [])) <= 512:
        return None
    images = []
    for page in pages:
        with Image.open(io.BytesIO(page)) as image:
            if image.mode != "RGBA" or max(image.size) > 2048:
                return None
            images.append(image.getchannel("A"))
    measured = []
    for frame in manifest["frame_rects"]:
        x, y, width, height = frame["rect"]
        alpha = images[frame.get("page", 0)].crop((x, y, x + width, y + height))
        measured.append(head_width(alpha))
    valid = [value for value in measured if value is not None]
    if len(valid) < len(measured) * 0.75:
        return None
    # 2、以头宽 38 世界单位统一体型，保留原脚底与小跑腾空；站坐不会被统一拉成同样身高。
    unit = manifest["display_height"] / manifest["frame_size"][1]
    pivot_x, pivot_y = manifest["pivot"]
    geometry = []
    for frame, head in zip(manifest["frame_rects"], measured, strict=True):
        width, height = frame["rect"][2:]
        old_scale = frame.get("scale", 1)
        scale = 38 / ((head or statistics.median(valid)) * unit)
        scale = max(old_scale * 0.4, min(old_scale * 2, scale))
        root = (pivot_x - frame["offset"][0]) / old_scale
        flight = max(0, pivot_y - frame["offset"][1] - height * old_scale)
        geometry.append(
            {
                "offset": [pivot_x - root * scale, pivot_y - height * scale - flight],
                "scale": scale,
                "head_width": (head or statistics.median(valid)) * scale * unit,
            }
        )
    # 3、泡泡按整套姿态缓存稳定挂点，不能再追逐单帧裁切或手臂摆动。
    sockets = {}
    for posture in ("standing", "seated"):
        tops = [
            (geometry[index]["offset"][1] - pivot_y) * unit
            for clip in manifest["clips"]
            if clip["posture"] == posture
            for index in clip["frames"]
        ]
        sockets[posture] = statistics.median(tops) if tops else -96
    return {"version": 1, "frames": geometry, "sockets": sockets}
