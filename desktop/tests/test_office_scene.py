"""办公室模板、接触方向和旧用户布局迁移验证。"""

import json
import math
from itertools import pairwise
from pathlib import Path

from roomcrew_desktop.assets.scene_catalog import footprint
from roomcrew_desktop.presentation.scene import SceneStore, anchors, default_room, path_to


def test_office_has_aligned_desks_reachable_seats_and_clear_main_aisle() -> None:
    """因为工位整齐不等于通道可走，需要同时检查方阵、家具占地、工作朝向和全部接近点。"""
    # 1、四个员工工位构成两行两列，安全台独立于员工，归档区不是装饰书架。
    room = default_room()
    objects = {item["id"]: item for item in room["objects"]}
    assert {(objects[f"desk-{i}"]["x"], objects[f"desk-{i}"]["y"]) for i in range(1, 5)} == {
        (3, 8),
        (8, 8),
        (3, 13),
        (8, 13),
    }
    assert objects["guardian-station"]["type"] == "security"
    occupied = set()
    for obj in room["objects"]:
        width, depth = footprint(obj)
        cells = {(obj["x"] + dx, obj["y"] + dy) for dx in range(width) for dy in range(depth)}
        assert not cells & occupied
        occupied.update(cells)
    # 2、主通道整列可走；工位统一面向显示器，所有座位的接近点都可从入口到达。
    assert not {(14, y) for y in range(room["height"])} & occupied
    for anchor in anchors(room):
        assert path_to(room, [0, 0], anchor["approach"])
        if anchor.get("purpose") == "workstation":
            assert anchor["direction"] == "nw"
        if anchor.get("purpose") == "meeting":
            assert anchor["direction"] in {"sw", "ne"}


def test_office_upgrade_keeps_custom_layouts_and_migrates_stock_placements(tmp_path: Path) -> None:
    """因为升级不能覆盖用户布置，需要验证默认旧布局迁移和自定义场景保护各自独立。"""
    # 1、通过当前默认生成旧版位置，模拟已持久化的标准模板与一个已有主人物。
    room = default_room()
    room["width"], room["height"] = 24, 19
    previous = {
        "desk-3": ("desk", 8, 13),
        "sofa": ("sofa", 2, 15),
        "conference": ("meeting", 16, 3),
        "guardian-station": ("cabinet", 19, 14),
        "fridge": ("fridge", 21, 10),
        "screen": ("screen", 16, 1),
        "plant-3": ("plant", 14, 15),
        "reading-shelf": ("bookcase", 1, 11),
        "reading-lamp": ("lamp", 1, 17),
        "archive-room": ("archive", 20, 1),
        "lounge-sofa": ("sofa", 16, 16),
        "coffee-corner": ("coffee", 22, 13),
        "lounge-plant": ("plant", 22, 17),
    }
    room["objects"] = [
        obj
        for obj in room["objects"]
        if obj["id"] not in {"desk-4", "lounge-west-sofa", "lounge-east-sofa", "lounge-tea-table"}
    ]
    for obj in room["objects"]:
        obj.pop("direction", None)
        if obj["id"] in previous:
            obj["type"], obj["x"], obj["y"] = previous[obj["id"]]
    for custom in (False, True):
        path = tmp_path / f"scene-{custom}.sqlite"
        store = SceneStore(path)
        with store.db:
            store.db.execute("UPDATE room SET body=?", (json.dumps(room),))
            store.db.execute(
                "INSERT INTO placements VALUES(?,?)",
                (
                    "assistant",
                    json.dumps(
                        {"member_id": "assistant", "anchor_id": "reception-desk", "generation": 3}
                    ),
                ),
            )
            if custom:
                changed = json.loads(json.dumps(room))
                changed["objects"][0]["x"] = 4
                store.db.execute("UPDATE room SET body=?", (json.dumps(changed),))
        store.close()
        reopened = SceneStore(path)
        try:
            snapshot = reopened.snapshot([])
            guardian = next(
                obj for obj in snapshot["room"]["objects"] if obj["id"] == "guardian-station"
            )
            assert guardian["type"] == ("cabinet" if custom else "security")
            place = snapshot["placements"][0]
            assert place["anchor_id"] == "reception-desk"
            assert place["generation"] == (3 if custom else 4)
        finally:
            reopened.close()


def test_routes_and_seated_contacts_keep_body_clearance() -> None:
    """因为整数格边界可让人物贴桌穿模，需要验证格心路线和所有座位都保留身体的实际地面余量。"""
    # 1、对全部座位之间的真实路线检查每段中点，不仅检查可达与整数节点。
    room = default_room()
    seats = anchors(room)
    for source in seats:
        assert len(source["position"]) == 2
        if source["posture"] == "seated":
            assert source["contact"]["feet"] == "ground"
        for target in seats:
            route = path_to(room, source["approach"], target["approach"])
            points = [[x + 0.5, y + 0.5] for x, y in route]
            samples = points + [[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] for a, b in pairwise(points)]
            for x, y in samples:
                for obj in room["objects"]:
                    width, height = footprint(obj)
                    dx = max(obj["x"] - x, 0, x - obj["x"] - width)
                    dy = max(obj["y"] - y, 0, y - obj["y"] - height)
                    assert math.hypot(dx, dy) >= 0.4
