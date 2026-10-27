"""人物级动作帧绑定；独立于后端 Agent 能力配置。"""

from typing import Any

from roomcrew_desktop.presentation.contracts import GESTURES

CATEGORIES = frozenset(
    {"tool", "python", "mcp", "skill", "human", "completed", "security", "directory"}
)


def material_profile(value: Any, avatar_id: str, manifest: dict[str, Any] | None) -> dict[str, Any]:
    """因为同一 Agent 可以对应不同素材，需要验证每个人物独立的动作、变体和帧序列。"""
    # 1、没有配置时沿用默认映射；更换图集后不能把旧帧号误用于新图片。
    if not isinstance(value, dict) or set(value) - {"version", "avatar_id", "bindings"}:
        raise ValueError("员工素材配置字段无效")
    if type(value.get("version", 1)) is not int or value.get("version", 1) != 1:
        raise ValueError("员工素材配置版本无效")
    bindings = value.get("bindings", {})
    if not isinstance(bindings, dict) or set(bindings) - CATEGORIES:
        raise ValueError("动作触发类型无效")
    if bindings and value.get("avatar_id", avatar_id) != avatar_id:
        raise ValueError("动作帧属于另一套素材，请重新配置")
    normalized = {}
    # 2、只接受已导入图集中的精确变体和有效帧，帧率与循环均为纯显示数据。
    for category, binding in bindings.items():
        if not isinstance(binding, dict) or set(binding) - {
            "action",
            "clip",
            "frames",
            "fps",
            "loop",
        }:
            raise ValueError("动作帧配置字段无效")
        action = binding.get("action")
        if not isinstance(action, str) or action not in GESTURES:
            raise ValueError("动作不在素材词表中")
        result: dict[str, Any] = {"action": action}
        if set(binding) - {"action"}:
            clips = manifest.get("clips", []) if manifest else []
            clip = next((item for item in clips if clip_key(item) == binding.get("clip")), None)
            if clip is None or clip["action"] != action:
                raise ValueError("请选择当前图集中的动作变体")
            count = (
                len(manifest["frame_rects"])
                if manifest and manifest["version"] >= 2
                else (
                    manifest["atlas_size"][0]
                    // manifest["frame_size"][0]
                    * (manifest["atlas_size"][1] // manifest["frame_size"][1])
                    if manifest
                    else 0
                )
            )
            frames = binding.get("frames", clip["frames"])
            fps, loop = binding.get("fps", clip["fps"]), binding.get("loop", clip["loop"])
            if (
                not isinstance(frames, list)
                or not 1 <= len(frames) <= 120
                or any(type(frame) is not int or not 0 <= frame < count for frame in frames)
            ):
                raise ValueError("动作帧号越界或数量超过 120")
            if type(fps) is not int or not 1 <= fps <= 60 or not isinstance(loop, bool):
                raise ValueError("帧率需要 1～60 的整数，循环需要布尔值")
            result.update(clip=clip_key(clip), frames=list(frames), fps=fps, loop=loop)
        normalized[category] = result
    return {"version": 1, "avatar_id": avatar_id, "bindings": normalized}


def clip_key(clip: dict[str, Any]) -> str:
    """因为动作变体需要稳定引用，需要用动作、方向、姿态和表情组成素材内唯一键。"""
    # 1、该键只引用已校验的有限字段，不是本地文件路径。
    return ".".join(clip[field] for field in ("action", "direction", "posture", "expression"))
