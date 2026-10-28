"""PNG 图集与动作清单的统一约束，不接受脚本或外部资源。"""

import math
from typing import Any

from roomcrew_desktop.assets.paths import atlas_filenames
from roomcrew_desktop.presentation.contracts import DIRECTIONS, EXPRESSIONS, GESTURES, POSTURES


def integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    """因为 JSON 布尔值也可被 Python 当整数，需要严格验证素材数值边界。"""
    # 1、只接受整数，防止非有限数、字符串和超界帧号进入渲染器。
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label}必须是 {minimum}～{maximum} 的整数")
    return value


def validate_manifest(value: Any, size: tuple[int, int] | list[tuple[int, int]]) -> dict[str, Any]:
    """因为自制素材必须使用相同设计约束，需要校验图集尺寸、脚底锚点和每种动作变体。"""
    # 1、未知字段和外部路径直接拒绝，只保留数据清单，不加载任意资源描述器。
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] not in {1, 2, 3}
    ):
        raise ValueError("仅支持 roomcrew.avatar v1 / v2 / v3 素材")
    version = value["version"]
    fields = {"format", "version", "name", "frame_size", "pivot", "pixel_art", "clips"}
    fields.add("images" if version == 3 else "image")
    if (
        not isinstance(value, dict)
        or not fields <= set(value)
        or set(value) - fields - {"mirror_west", "frame_rects"}
    ):
        raise ValueError("素材清单字段不完整或包含未知字段")
    if "mirror_west" in value and not isinstance(value["mirror_west"], bool):
        raise ValueError("mirror_west 必须是布尔值")
    if (
        value["format"] != "roomcrew.avatar"
        or type(value["version"]) is not int
        or value["version"] not in {1, 2, 3}
    ):
        raise ValueError("仅支持 roomcrew.avatar v1 / v2 / v3 素材")
    if (version >= 2) != ("frame_rects" in value):
        raise ValueError("v2 / v3 素材需要 frame_rects，v1 保留等格图集")
    if not isinstance(value["name"], str) or not 1 <= len(value["name"].strip()) <= 40:
        raise ValueError("素材名称长度应为 1～40 字")
    filenames = atlas_filenames(value)
    sizes = size if isinstance(size, list) else [size]
    if len(sizes) != len(filenames) or any(len(item) != 2 for item in sizes):
        raise ValueError("图集页与尺寸数量不一致")
    if not isinstance(value["pixel_art"], bool):
        raise ValueError("pixel_art 必须是布尔值")
    # 2、统一帧尺寸与脚底锚点，显示高度由播放器归一到世界尺度。
    frame = value["frame_size"]
    pivot = value["pivot"]
    if (
        not isinstance(frame, list)
        or len(frame) != 2
        or not isinstance(pivot, list)
        or len(pivot) != 2
    ):
        raise ValueError("frame_size 和 pivot 必须是两个整数")
    width = integer(frame[0], 32, 512, "帧宽")
    height = integer(frame[1], 48, 512, "帧高")
    integer(pivot[0], 0, width, "脚底 X")
    integer(pivot[1], height // 2, height, "脚底 Y")
    if version >= 2:
        count = validate_frame_rects(value["frame_rects"], sizes, (width, height), version == 3)
    else:
        if sizes[0][0] % width or sizes[0][1] % height:
            raise ValueError("图集宽高必须是单帧尺寸的整数倍")
        count = sizes[0][0] // width * (sizes[0][1] // height)
    clips = value["clips"]
    if not isinstance(clips, list) or not 1 <= len(clips) <= 128:
        raise ValueError("每个素材需要 1～128 个动作变体")
    # 3、动作、方向、表情、坐姿分开描述；缺失变体由播放器明确回退。
    seen = set()
    total = 0
    normalized = []
    for clip in clips:
        expected = {"action", "direction", "posture", "expression", "frames", "fps", "loop"}
        if not isinstance(clip, dict) or set(clip) != expected:
            raise ValueError("动作变体字段无效")
        if any(
            not isinstance(clip[key], str)
            for key in ("action", "direction", "posture", "expression")
        ):
            raise ValueError("动作词表字段必须是字符串")
        if clip["action"] not in GESTURES or clip["direction"] not in DIRECTIONS:
            raise ValueError("动作或朝向不在注册词表中")
        if clip["posture"] not in POSTURES or clip["expression"] not in EXPRESSIONS:
            raise ValueError("姿态或表情不在注册词表中")
        key = tuple(clip[field] for field in ("action", "direction", "posture", "expression"))
        if key in seen:
            raise ValueError("动作变体重复")
        seen.add(key)
        frames = clip["frames"]
        if not isinstance(frames, list) or not 1 <= len(frames) <= 120:
            raise ValueError("每个动作需要 1～120 帧")
        for index in frames:
            integer(index, 0, count - 1, "图集帧号")
        integer(clip["fps"], 1, 60, "动作帧率")
        if not isinstance(clip["loop"], bool):
            raise ValueError("loop 必须是布尔值")
        total += len(frames)
        normalized.append(dict(clip))
    if total > 2048 or not any(
        clip["action"] == "idle" and clip["posture"] == "standing" for clip in clips
    ):
        raise ValueError("必须提供站立 idle，且总帧引用不能超过 2048")
    return {
        **value,
        "name": value["name"].strip(),
        "clips": normalized,
        **(
            {"atlas_sizes": [list(item) for item in sizes]}
            if version == 3
            else {"atlas_size": list(sizes[0])}
        ),
        "display_height": 128,
    }


def validate_frame_rects(
    value: Any, sizes: list[tuple[int, int]], frame: tuple[int, int], paged: bool = False
) -> int:
    """因为手绘帧的留白与裁切尺寸不同，需要严格验证每帧源区域与统一虚拟画布内的偏移。

    返回有效帧数；越界、未知字段、布尔数值和过量矩形抛出 ValueError，不修改原图。
    """
    # 1、控制矩形数量与字段，裁切元数据不能引入额外文件或可执行行为。
    if not isinstance(value, list) or not 1 <= len(value) <= 512:
        raise ValueError("frame_rects 需要 1—512 个裁切描述")
    for item in value:
        expected = {"rect", "offset", "page", "scale"} if paged else {"rect", "offset"}
        if (
            not isinstance(item, dict)
            or not expected <= set(item)
            or set(item) - expected - {"contact"}
        ):
            raise ValueError("裁切描述字段不匹配")
        page = integer(item["page"], 0, len(sizes) - 1, "图集页号") if paged else 0
        size = sizes[page]
        scale = item["scale"] if paged else 1
        if type(scale) not in {int, float} or not math.isfinite(scale) or not 0.25 <= scale <= 2:
            raise ValueError("帧缩放必须是 0.25—2 的有限数值")
        rect, offset = item["rect"], item["offset"]
        if (
            not isinstance(rect, list)
            or len(rect) != 4
            or not isinstance(offset, list)
            or len(offset) != 2
        ):
            raise ValueError("裁切区域和偏移维度无效")
        # 2、源矩形必须完全位于受约束图集，目标矩形完全位于统一虚拟帧。
        x = integer(rect[0], 0, size[0] - 1, "源 X")
        y = integer(rect[1], 0, size[1] - 1, "源 Y")
        width = integer(rect[2], 1, min(512, size[0] - x), "裁切宽")
        height = integer(rect[3], 1, min(512, size[1] - y), "裁切高")
        integer(offset[0], 0, frame[0], "帧内 X")
        integer(offset[1], 0, frame[1], "帧内 Y")
        if offset[0] + width * scale > frame[0] or offset[1] + height * scale > frame[1]:
            raise ValueError("缩放后的裁切区域超出虚拟画布")
        if "contact" in item:
            validate_frame_contact(item["contact"], frame)
    return len(value)


def validate_frame_contact(value: Any, frame: tuple[int, int]) -> None:
    """因为自制坐姿也要能匹配座面，需要允许有限的髋部、脚底、手部和泡泡标记，拒绝脚本与非数值。"""
    # 1、标记使用统一虚拟帧坐标，不包含文件路径或运行权限。
    if (
        not isinstance(value, dict)
        or not {"hip", "soles"} <= set(value)
        or set(value) - {"hip", "soles", "hands", "bubble"}
    ):
        raise ValueError("接触标记必须包含 hip 和 soles")
    for point in value.values():
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("接触标记需要二维坐标")
        if any(
            type(coordinate) not in {int, float}
            or not math.isfinite(coordinate)
            or not 0 <= coordinate <= frame[axis]
            for axis, coordinate in enumerate(point)
        ):
            raise ValueError("接触标记超出虚拟画布")
    # 2、坐姿必须有正向臀部到脚底高度，避免零腿长或颠倒接触进入求解器。
    if not value["hip"][1] < value["soles"][1]:
        raise ValueError("臀部需要高于脚底")
