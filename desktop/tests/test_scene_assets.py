"""统一八向素材、旋转占地、接触标记与旧空间迁移验收。"""

import json
import math
import statistics
from pathlib import Path

import pytest
from PIL import Image

from roomcrew_desktop.assets.scene_catalog import DIRECTIONS, footprint, scene_catalog
from roomcrew_desktop.assets.schema import validate_frame_contact
from roomcrew_desktop.presentation.scene import SceneStore, anchors, default_room, path_to

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "desktop/ui/studio/assets/scene-v1"


def test_shared_catalog_has_real_bounded_direction_frames() -> None:
    """因为八个方向不能只是复制八次文件名，需要核查独立裁切、原绘/对称声明和真实源范围。"""
    # 1、原生 JSON 与浏览器目录内容一致，全部设备进入同一合同。
    data = scene_catalog()
    wrapped = json.loads(
        (ASSETS / "catalog.js").read_text("utf-8").split("=", 1)[1].strip().rstrip(";")
    )
    assert data == wrapped
    assert len(data["definitions"]) == 14
    for material in data["materials"].values():
        assert set(material["views"]) == set(DIRECTIONS)
        source = (ASSETS.parent / "library-v1" / material["image"]).resolve()
        assert source.is_relative_to((ROOT / "desktop/ui").resolve())
        with Image.open(source) as picture:
            assert list(picture.size) == material["atlas_size"]
        for view in material["views"].values():
            view_source = (
                ASSETS.parent / "library-v1" / view.get("image", material["image"])
            ).resolve()
            assert view_source.is_relative_to((ROOT / "desktop/ui").resolve())
            with Image.open(view_source) as picture:
                assert list(picture.size) == view.get("atlas_size", material["atlas_size"])
                x, y, width, height = view["rect"]
                assert x >= 0 and y >= 0 and width > 0 and height > 0
                assert x + width <= picture.width and y + height <= picture.height
        if material["views"]["se"]["coverage"] == "drawn":
            assert len({tuple(view["rect"]) for view in material["views"].values()}) == 8
    # 2、桌子每向的操作面来自素材登记，不能在渲染器复用一组正面偏移。
    for kind in ("desk", "security"):
        points = [
            tuple(view["operator_ground"]) for view in data["materials"][kind]["views"].values()
        ]
        assert len(set(points)) == 8


def measured_top_edge(path: Path, left: int, right: int) -> float:
    """因为素材目录里的角度标签不能证明原图正确，需要只读采样真实透明轮廓并拟合硬边斜率。

    区间由默认桌子的两条无遮挡后沿选定；返回角度，不修改像素或依赖登记的角度常量。
    """
    # 1、透明噪点不属于实体边缘；每列取第一个明确不透明像素。
    with Image.open(path) as picture:
        alpha = picture.getchannel("A")
        values = []
        for x in range(left, right):
            for y in range(alpha.height):
                if alpha.getpixel((x, y)) >= 100:
                    values.append((x, y))
                    break
    # 2、最小二乘使用完整边缘区间，不能只挑两个巧合像素来宣称轴线通过。
    assert len(values) == right - left
    mean_x = statistics.mean(point[0] for point in values)
    mean_y = statistics.mean(point[1] for point in values)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in values) / sum(
        (x - mean_x) ** 2 for x, _ in values
    )
    return math.degrees(math.atan(slope))


def test_rebuilt_workstation_pixels_align_to_ground_axes() -> None:
    """因为旧桌子与地板透视不一致，需要直接核查新默认源图硬边，而不是只验证渲染器没有拉伸。"""
    # 1、两条无遮挡后沿分别朝向地砖的两个轴，允许手绘边线一度误差。
    source = ASSETS.parent / "scene-v2/workstation-se.png"
    angle = math.degrees(math.atan(0.5))
    assert abs(measured_top_edge(source, 260, 450) + angle) < 1
    assert abs(measured_top_edge(source, 1030, 1150) - angle) < 1


def test_rebuilt_seats_use_physical_origin_and_table_edge_contacts() -> None:
    """因为换图后座面与地面不能各自猜偏移，需要验证每向的物理座高及会议桌实际侧边座位。"""
    # 1、坐具每向投影高度可以不同，座面到根点的物理高度始终是旧角色兼容规格 22。
    data = scene_catalog()
    for kind in ("chair", "sofa"):
        for view in data["materials"][kind]["views"].values():
            assert view["camera_profile_id"] == "rc-ortho-2to1-v1"
            assert abs((view["ground"][1] - view["seat"][1]) * view["display_height"] - 22) < 1e-8
            assert view["physical_profile"] == "legacy-character-seat22"
    # 2、会议席距桌子中心应为实体侧边加椅子间距，不能沿五乘六的大占地边界悬空排队。
    room = default_room()
    table = next(obj for obj in room["objects"] if obj["type"] == "meeting")
    width, depth = footprint(table)
    center = [table["x"] + width / 2, table["y"] + depth / 2]
    seats = [anchor for anchor in anchors(room) if anchor["object_id"] == table["id"]]
    assert len(seats) == 4
    for seat in seats:
        assert abs(abs(seat["position"][0] - center[0]) - 1.0) < 1e-8
        assert abs(abs(seat["position"][1] - center[1]) - 1.65) < 1e-8


@pytest.mark.parametrize("kind", ["desk", "chair", "sofa", "meeting", "screen", "tea_table"])
def test_eight_rotations_persist_geometry_and_reachable_contacts(tmp_path: Path, kind: str) -> None:
    """因为用户会反复转向后重启，需要核查每向占地、接近点和持久化方向，不能只改变图片。"""
    # 1、隔离的空会议室允许验证每个方向，避免现有家具占用影响旋转结果。
    store = SceneStore(tmp_path / "scene.sqlite")
    with store.db:
        store.db.execute(
            "UPDATE room SET body=?",
            (json.dumps({"width": 32, "height": 25, "revision": 1, "objects": []}),),
        )
    identifier = None
    for index, direction in enumerate(DIRECTIONS):
        values = {"type": kind, "x": 10, "y": 10, "direction": direction, "seat_height": 23}
        if identifier:
            values["id"] = identifier
        updated = store.edit(values, index + 1)
        obj = updated["objects"][0]
        identifier = obj["id"]
        assert obj["direction"] == direction
        assert all(value > 0 for value in footprint(obj))
        for anchor in anchors(updated):
            assert path_to(updated, [0, 0], anchor["approach"])
            if anchor["posture"] == "seated":
                assert anchor["contact"]["seat_height"] == 23
    store.close()
    reopened = SceneStore(tmp_path / "scene.sqlite")
    try:
        obj = reopened.snapshot([])["room"]["objects"][0]
        assert obj["id"] == identifier and obj["direction"] == DIRECTIONS[-1]
    finally:
        reopened.close()


def test_four_sofas_face_central_table_without_blocking_routes() -> None:
    """因为增加两张沙发不能只堆在角落，需要验证相向布局、中心茶几和四个接近点。"""
    # 1、默认布景以四种正面朝向围住中间茶几，仍保留旧两张沙发的 ID。
    room = default_room()
    sofas = [obj for obj in room["objects"] if obj["type"] == "sofa"]
    assert len(sofas) == 4
    assert {obj["direction"] for obj in sofas} == {"se", "sw", "ne", "nw"}
    assert {"sofa", "lounge-sofa"} <= {obj["id"] for obj in sofas}
    assert len([obj for obj in room["objects"] if obj["type"] == "tea_table"]) == 1
    for anchor in anchors(room):
        assert path_to(room, [0, 0], anchor["approach"])


def test_scene_scale_and_working_frames_have_consistent_contact() -> None:
    """因为过去各家具按任意高度缩放造成比例失衡，需要验证相对尺度及新工作坐姿的真实来源和接触。"""
    # 1、双人沙发不再缩成单椅，茶几与办公椅在统一比例范围，不把大阴影作为家具尺寸。
    data = scene_catalog()
    heights = {kind: value["height"] for kind, value in data["definitions"].items()}
    assert 0.9 <= heights["sofa"] / heights["desk"] <= 1.1
    assert 0.5 <= heights["tea_table"] / heights["sofa"] <= 0.65
    assert 0.45 <= heights["chair"] / heights["desk"] <= 0.6
    # 2、工作补图每角色四帧、两个真实方向，原图存在并有臀部、脚底和双手登记。
    for person in data["characters"].values():
        work = person["working"]
        assert len(work["frames"]) == 4
        assert [frame["direction"] for frame in work["frames"]] == ["nw", "nw", "ne", "ne"]
        with Image.open(ASSETS / Path(work["image"]).name) as picture:
            assert list(picture.size) == work["size"]
            assert picture.mode == "RGBA"
        for frame in work["frames"]:
            assert {"hip", "soles", "hands", "seat_height"} <= set(frame["contact"])
            # 3、该旧字段是投影中臀部至鞋底的纵向距离，不是物理座高，不能用它强行塞脚踏。
            assert 8 <= frame["contact"]["seat_height"] <= 36


def test_custom_contact_annotations_reject_nonfinite_or_inverted_geometry() -> None:
    """因为未来用户会自制坐姿，需要允许明确标记同时拒绝无意义或非有限接触坐标。"""
    # 1、标记在虚拟帧内，臀部高于脚底；不能夹带路径或脚本。
    validate_frame_contact({"hip": [100, 160], "soles": [100, 196]}, (200, 200))
    for value in (
        {"hip": [100, 200], "soles": [100, 160]},
        {"hip": [float("nan"), 10], "soles": [100, 196]},
        {"hip": [True, 160], "soles": [100, 196]},
        {"hip": [100, 160], "soles": [100, 196], "script": "x"},
    ):
        with pytest.raises(ValueError):
            validate_frame_contact(value, (200, 200))


def test_paired_chair_actions_have_alpha_bounds_and_real_standing_handoff() -> None:
    """因为配套片段替代独立人物与椅子的拼接，需要核查实际透明源、帧数、定位和鞋底交接。"""
    # 1、四角色都具备完整六帧起坐和配套工作姿势，不能只给助手增加一个截图素材。
    for person in scene_catalog()["characters"].values():
        for kind, count in (("paired", 4), ("transition", 6)):
            entry = person[kind]
            assert len(entry["frames"]) == count
            with Image.open(ROOT / "desktop/ui" / entry["image"]) as picture:
                assert list(picture.size) == entry["size"]
                assert picture.getchannel("A").getextrema()[0] == 0
                for frame in entry["frames"]:
                    x, y, width, height = frame["rect"]
                    assert 0 <= x < x + width <= picture.width
                    assert 0 <= y < y + height <= picture.height
                    assert frame["includes_seat"] is True
                    assert frame["seat_style"] == "sage-chair-v1"
                    assert frame["scale"] > 0
        # 2、椅脚至鞋底的投影差由各角色原图登记，不能给每个角色硬塞统一偏移。
        x, y = person["transition"]["standing_foot"]
        assert -30 < x < -10 and -6 < y < 6


def test_lounge_upgrade_only_changes_known_template(tmp_path: Path) -> None:
    """因为升级不能覆盖用户自己的布置，需要核查已知旧模板升级与移动过家具的场景保护。"""
    # 1、还原前一版标准模板，不复制任何真实用户数据库或会话。
    room = default_room()
    room.update(width=24, height=19)
    old = {
        "sofa": (16, 12),
        "lounge-sofa": (16, 16),
        "fridge": (22, 15),
        "coffee-corner": (22, 13),
        "reading-lamp": (15, 16),
        "lounge-plant": (22, 17),
    }
    room["objects"] = [
        obj
        for obj in room["objects"]
        if obj["id"] not in {"lounge-west-sofa", "lounge-east-sofa", "lounge-tea-table"}
    ]
    for obj in room["objects"]:
        obj.pop("direction", None)
        if obj["id"] == "plant-3":
            obj["y"] = 13
        if obj["id"] in old:
            obj["x"], obj["y"] = old[obj["id"]]
    for custom in (False, True):
        path = tmp_path / f"scene-{custom}.sqlite"
        store = SceneStore(path)
        body = json.loads(json.dumps(room))
        if custom:
            body["objects"][0]["x"] += 1
        with store.db:
            store.db.execute("UPDATE room SET body=?", (json.dumps(body),))
        store.close()
        reopened = SceneStore(path)
        try:
            saved = reopened.snapshot([])["room"]
            assert len([obj for obj in saved["objects"] if obj["type"] == "sofa"]) == (
                2 if custom else 4
            )
        finally:
            reopened.close()


def test_chair_clearance_upgrade_preserves_custom_layout(tmp_path: Path) -> None:
    """因为拉椅不能碰到旧默认盆栽，需要只迁移原模板并保护用户装修。"""
    # 1、同一旧模板分别模拟未修改和用户移动过桌子的情况。
    for custom in (False, True):
        body = default_room()
        next(obj for obj in body["objects"] if obj["id"] == "plant-3")["y"] = 13
        if custom:
            body["objects"][0]["x"] += 1
        path = tmp_path / f"chair-clearance-{custom}.sqlite"
        store = SceneStore(path)
        with store.db:
            store.db.execute("UPDATE room SET body=?", (json.dumps(body),))
        store.close()
        reopened = SceneStore(path)
        try:
            plant = next(
                obj for obj in reopened.snapshot([])["room"]["objects"] if obj["id"] == "plant-3"
            )
            assert plant["y"] == (13 if custom else 11)
        finally:
            reopened.close()
