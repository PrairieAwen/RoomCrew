"""统一场景素材合同：方向、占地、座位与能力；不依赖 Agent 或界面播放器。"""

import json
import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

DIRECTIONS = ("e", "se", "s", "sw", "w", "nw", "n", "ne")
VECTORS = ((1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1))


@lru_cache(maxsize=1)
def scene_catalog() -> dict[str, Any]:
    """因为原生校验和画布需要同一份素材事实，需要从随包只读 JSON 读取定义而不是维护两套常量。"""
    # 1、资源路径不来自模型、工作目录或用户任务文件。
    bundle = getattr(sys, "_MEIPASS", None)
    root = Path(bundle) if bundle else Path(__file__).resolve().parents[4]
    path = root / "desktop/ui/studio/assets/scene-v1/catalog.json"
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    if data.get("format") != "roomcrew.scene-assets" or data.get("version") != 1:
        raise ValueError("场景素材目录版本不兼容")
    return data


def object_direction(obj: dict[str, Any]) -> str:
    """因为旧布置未保存方向，需要显式使用该素材的默认面而不是猜测图片朝向。"""
    # 1、未知方向直接报错，不能保存后在渲染端悄悄改成另一面。
    definition = scene_catalog()["definitions"][obj["type"]]
    direction = obj.get("direction", definition["default_direction"])
    if direction not in DIRECTIONS:
        raise ValueError("家具方向必须是八方向之一")
    return str(direction)


def footprint(obj: dict[str, Any]) -> tuple[int, int]:
    """因为旋转会改变实际占地，需要从本地方向计算保守的格网外沿，禁止只旋转图片。"""
    # 1、四十五度使用旋转矩形外包格；方形与圆形按各自的旋转对称定义处理。
    definition = scene_catalog()["definitions"][obj["type"]]
    width, depth = definition["footprint"]
    if definition.get("rotation_symmetric"):
        return int(width), int(depth)
    angle = (
        (DIRECTIONS.index(object_direction(obj)) - DIRECTIONS.index(definition["base_direction"]))
        * math.pi
        / 4
    )
    cosine, sine = abs(math.cos(angle)), abs(math.sin(angle))
    return math.ceil(width * cosine + depth * sine - 1e-8), math.ceil(
        width * sine + depth * cosine - 1e-8
    )


def interaction_anchors(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """因为家具正面改变后人物也要从正确一侧接近，需要统一派生可达点、坐姿接触与朝向。"""
    # 1、步行接近点在占地之外，座位使用保留的前缘空间；索引是整数，实际脚点在格心。
    definition = scene_catalog()["definitions"][obj["type"]]
    role = definition.get("interaction")
    if not role:
        return []
    width, depth = footprint(obj)
    direction = object_direction(obj)
    dx, dy = VECTORS[DIRECTIONS.index(direction)]
    center = [obj["x"] + width / 2, obj["y"] + depth / 2]
    reach = min(
        (width / 2 + 0.5) / abs(dx) if dx else 100, (depth / 2 + 0.5) / abs(dy) if dy else 100
    )
    front = [math.floor(center[0] + dx * reach), math.floor(center[1] + dy * reach)]
    facing = (
        direction
        if role in {"lounge", "chair"}
        else DIRECTIONS[(DIRECTIONS.index(direction) + 4) % 8]
    )
    points = [(front, facing)]
    # 2、会议桌四席使用两侧相向座位，沿同一方向合同旋转；沙发先提供一个稳定主座位。
    if role == "meeting":
        points = []
        for sign in (-1, 1):
            for offset in (-1, 1):
                point = [
                    math.floor(center[0] + sign * dx * reach - dy * offset),
                    math.floor(center[1] + sign * dy * reach + dx * offset),
                ]
                look = DIRECTIONS[(DIRECTIONS.index(direction) + (4 if sign > 0 else 0)) % 8]
                points.append((point, look))
    result = []
    for index, (point, look) in enumerate(points):
        # 3、占地含座椅实体，步行接近点在外侧，真正入座点在保留的前缘半格，不能让别人穿过椅脚。
        if role == "meeting":
            side = -1 if index < 2 else 1
            layout = definition.get("seat_layout")
            if layout:
                # 座点采用实体桌边；接近点仍在保守占地外，两者不能因为共用大矩形而混成同一位置。
                normal = math.hypot(dx, dy)
                lateral = -1 if index % 2 == 0 else 1
                forward = side * layout["distance"] / normal
                across = lateral * layout["span"] / normal
                position = [
                    center[0] + dx * forward - dy * across,
                    center[1] + dy * forward + dx * across,
                ]
            else:
                position = [point[0] + 0.5 - side * dx * 0.45, point[1] + 0.5 - side * dy * 0.45]
        else:
            inset = 0.7 if role == "workstation" else 1.0
            position = [point[0] + 0.5 - dx * inset, point[1] + 0.5 - dy * inset]
        identifier = obj["id"] + (f":seat-{index + 1}" if role == "meeting" else "")
        result.append(
            {
                "id": identifier,
                "object_id": obj["id"],
                "approach": point,
                "position": position,
                "furniture_position": [point[0] + 0.5 - dx, point[1] + 0.5 - dy],
                "posture": "seated",
                "direction": look,
                "purpose": "workstation"
                if role == "workstation"
                else "lounge"
                if role == "lounge"
                else "meeting"
                if role == "meeting"
                else "chair",
                "contact": {
                    "seat_height": obj.get("seat_height", definition.get("seat_height", 22)),
                    "feet": "ground",
                },
            }
        )
    return result
