"""客户端人物属性；通用 Agent 服务不解释动作、外观和泡泡。"""

import re
from collections.abc import Callable
from typing import Any

from roomcrew.accounts.repository import AccountRepository
from roomcrew.accounts.service import AccountService
from roomcrew_desktop.assets.bindings import CATEGORIES, material_profile
from roomcrew_desktop.presentation.contracts import GESTURES, leisure_profile

INTERACTION_DEFAULTS = {
    "question_bubble": "老板，我有问题想问你。",
    "completed_bubble": "老板，本轮回复已就绪，请查看。",
    "action_overrides": {},
}


def interaction_profile(value: Any) -> dict[str, Any]:
    """因为人物短提示与动作应由客户端决定，需要验证有限文本和可覆盖的素材动作。"""
    # 1、缺省值兼容旧人物，不把模型输出当作自定义动作定义。
    if not isinstance(value, dict) or set(value) - set(INTERACTION_DEFAULTS):
        raise ValueError("人物交互配置字段无效")
    profile = {**INTERACTION_DEFAULTS, **value}
    # 旧默认文案把框架结束误写成业务成功；只兼容这一精确旧值，保留其他用户文案。
    if profile["completed_bubble"] == "老板，我干完了，你看看。":
        profile["completed_bubble"] = INTERACTION_DEFAULTS["completed_bubble"]
    for key in ("question_bubble", "completed_bubble"):
        if not isinstance(profile[key], str) or not 1 <= len(profile[key]) <= 80:
            raise ValueError("聊天泡泡需要 1～80 字短提示")
    # 2、只接受已注册动作，禁止表达式、脚本或任意帧指令。
    overrides = profile["action_overrides"]
    if not isinstance(overrides, dict) or any(
        key not in CATEGORIES or not isinstance(item, str) or item not in GESTURES
        for key, item in overrides.items()
    ):
        raise ValueError("动作映射需要已注册的类别和动作")
    return {**profile, "action_overrides": dict(overrides)}


class DesktopAccountService(AccountService):
    attribute_fields = frozenset(
        {
            "color",
            "skin",
            "hair",
            "glasses",
            "avatar_id",
            "leisure_action",
            "leisure_actions",
            "leisure_delay",
            "interaction_profile",
            "material_profile",
        }
    )

    def __init__(
        self,
        repository: AccountRepository,
        avatar_validator: Callable[[str], None] | None = None,
        clip_catalog: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        """因为素材是桌面专属能力，需要把注册表校验接在客户端人员服务中。"""
        # 1、先准备扩展验证器，再让通用服务初始化最低身份。
        self._avatar_validator = avatar_validator
        self._clip_catalog = clip_catalog
        self.default_avatars: dict[str, str] = {}
        super().__init__(repository)

    def _attributes(self, values: dict[str, Any]) -> dict[str, Any]:
        """因为外观和泡泡不能成为后端执行策略，需要在客户端统一规范化人物扩展。"""
        # 1、颜色与素材只能来自受限值，不允许通过图片声明执行脚本。
        result: dict[str, Any] = {}
        for key, default in (("color", "#6d9785"), ("skin", "#edc39b"), ("hair", "#51443e")):
            candidate = values.get(key, default)
            if not isinstance(candidate, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
                raise ValueError("外观颜色必须是六位十六进制颜色")
            result[key] = candidate
        glasses = values.get("glasses", False)
        if not isinstance(glasses, bool):
            raise ValueError("眼镜开关必须是布尔值")
        avatar = values.get(
            "avatar_id", self.default_avatars.get(values.get("role", "employee"), "builtin:crew-v1")
        )
        if avatar != "builtin:crew-v1":
            if not isinstance(avatar, str) or self._avatar_validator is None:
                raise ValueError("请先导入并注册人物素材")
            self._avatar_validator(avatar)
        # 2、生活动作和短提示只存在人物表，Agent 执行快照不包含这些字段。
        return {
            **result,
            "glasses": glasses,
            "avatar_id": avatar,
            **leisure_profile(values),
            "interaction_profile": interaction_profile(values.get("interaction_profile", {})),
            "material_profile": material_profile(
                values.get("material_profile", {}),
                avatar,
                self._clip_catalog(avatar) if self._clip_catalog else None,
            ),
        }

    def members(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """因为旧人物没有交互配置，需要在客户端读取时提供兼容的显示默认值。"""
        # 1、不改写数据库，也不把执行提示加入场景广播。
        return [{**item, **self._attributes(item)} for item in super().members(include_archived)]

    def get(self, member_id: str) -> dict[str, Any]:
        """因为编辑旧人物需要完整默认属性，需要在通用定义之上补齐客户端字段。"""
        # 1、完整 Agent 配置只通过可信人工入口读取。
        item = super().get(member_id)
        return {**item, **self._attributes(item)}
