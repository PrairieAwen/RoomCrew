"""为美术验收建立隔离预览账号，不修改用户正式资料。"""

import asyncio
import sys
from pathlib import Path

sys.path[:0] = [
    str(Path(__file__).resolve().parents[3] / "backend/src"),
    str(Path(__file__).resolve().parents[3] / "desktop/src"),
]

from roomcrew.application.runtime import Runtime
from roomcrew.platform.paths import AppPaths


async def main() -> None:
    """因为四套角色需要在实际程序中一起查看，需要使用正式接口生成无模型配置的独立预览数据。"""
    # 1、目录固定在项目缓存；不接触默认 LOCALAPPDATA 数据或真实凭据。
    root = Path(__file__).resolve().parents[3] / ".cache/living-studio-preview"
    runtime = Runtime(AppPaths.create(root))
    await runtime.start()
    try:
        # 2、素材导入与人物绑定复用生产逻辑，不构造任务、轨迹或模型结果。
        for role, identifier, name, action in (
            ("owner", "material_colleague", "阿晨", "phone"),
            ("assistant", "assistant", "小禾", "phone"),
            ("guardian", "guardian", "监管员", "none"),
            ("employee", "material_employee", "小岚", "game"),
        ):
            asset = await runtime.import_avatar_bundle(role)
            previous = next(
                (item for item in runtime.accounts.members() if item["id"] == identifier), None
            )
            await runtime.save_member(
                {
                    "id": identifier,
                    "name": name,
                    "avatar_id": asset["id"],
                    "leisure_action": action,
                    "leisure_delay": 0,
                },
                previous["revision"] if previous else 0,
            )
        print(str(root))
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
