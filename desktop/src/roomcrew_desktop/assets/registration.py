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
    # 2、完整片段共享一个头部校准倍率，保留作者逐帧登记、脚底与腾空，不逐帧量头缩放。
    unit = manifest["display_height"] / manifest["frame_size"][1]
    factors = clip_factors(manifest, measured, unit)
    pivot_x, pivot_y = manifest["pivot"]
    geometry = []
    for index, (frame, head) in enumerate(zip(manifest["frame_rects"], measured, strict=True)):
        width, height = frame["rect"][2:]
        old_scale = frame.get("scale", 1)
        scale = old_scale * factors[index]
        root = (pivot_x - frame["offset"][0]) / old_scale
        flight = max(0, pivot_y - frame["offset"][1] - height * old_scale)
        geometry.append(
            {
                "offset": [pivot_x - root * scale, pivot_y - height * scale - flight],
                "scale": scale,
                "head_width": (head or statistics.median(valid)) * scale * unit,
            }
        )
        if "contact" in frame:
            # 3、自制标记随同一等比变换移动，不能在人物归一后继续使用旧帧坐标。
            points = {}
            for name, point in frame["contact"].items():
                points[name] = [
                    (
                        geometry[-1]["offset"][axis]
                        + (point[axis] - frame["offset"][axis]) / old_scale * scale
                        - (pivot_x if axis == 0 else pivot_y)
                    )
                    * unit
                    for axis in range(2)
                ]
            points["seat_height"] = points["soles"][1] - points["hip"][1]
            geometry[-1]["contact"] = points
    # 4、泡泡按整套姿态缓存稳定挂点，不能再追逐单帧裁切或手臂摆动。
    sockets = {}
    for posture in ("standing", "seated"):
        tops = [
            (geometry[index]["offset"][1] - pivot_y) * unit
            for clip in manifest["clips"]
            if clip["posture"] == posture
            for index in clip["frames"]
        ]
        sockets[posture] = statistics.median(tops) if tops else -96
    return {"version": 2, "strategy": "clip-median", "frames": geometry, "sockets": sockets}


def clip_factors(
    manifest: dict[str, Any], measured: list[float | None], unit: float
) -> list[float]:
    """因为背影、表情和道具会干扰单帧头宽估计，需要按动作/姿态/方向汇总固定倍率。

    保留作者原 scale；同组表情和所有共用帧的片段合并，未引用帧采用整包基准。
    """
    # 1、去重组内帧号，避免同一帧被多个表情引用后影响权重。
    groups: dict[tuple[str, str, str], set[int]] = {}
    frames = manifest["frame_rects"]
    for clip in manifest["clips"]:
        key = (clip["action"], clip["posture"], clip["direction"])
        groups.setdefault(key, set()).update(clip["frames"])
    valid = [
        head * frames[index].get("scale", 1) * unit
        for index, head in enumerate(measured)
        if head is not None
    ]
    fallback = 38 / statistics.median(valid)
    components: list[set[int]] = []
    for indices in groups.values():
        merged = set(indices)
        separate = []
        for component in components:
            if merged.isdisjoint(component):
                separate.append(component)
            else:
                merged.update(component)
        components = [*separate, merged]
    factors = [fallback] * len(frames)
    # 2、共用任意帧的片段只估算一次，防止一个 idle 帧因同时用于 report 而有不同倍率。
    for indices in components:
        widths = [
            measured[index] * frames[index].get("scale", 1) * unit
            for index in indices
            if measured[index] is not None
        ]
        factor = 38 / statistics.median(widths) if widths else fallback
        for index in indices:
            factors[index] = factor
    # 3、有界矫正保留特殊体型；无法可靠识别的整包已由调用方退出自动校准。
    return [max(0.4, min(2, factor)) for factor in factors]
