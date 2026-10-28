"""固定画布的布局、锚点、占座和有界格网路径；只影响空间表现。"""

import heapq
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from roomcrew_desktop.assets.scene_catalog import (
    DIRECTIONS,
    footprint,
    interaction_anchors,
    object_direction,
    scene_catalog,
)

CATALOG = {key: tuple(value["footprint"]) for key, value in scene_catalog()["definitions"].items()}


def default_room() -> dict[str, Any]:
    """因为首次打开需要完整办公布局，需要给固定画布配置可编辑的家具和会议区。"""
    # 1、所有家具遵循同一格网和投影，人物锚点由家具类型生成。
    return {
        "width": 32,
        "height": 25,
        "revision": 1,
        "objects": [
            {"id": "reception-desk", "type": "desk", "x": 3, "y": 2},
            {"id": "desk-1", "type": "desk", "x": 3, "y": 8},
            {"id": "desk-2", "type": "desk", "x": 8, "y": 8},
            {"id": "desk-3", "type": "desk", "x": 3, "y": 13},
            {"id": "desk-4", "type": "desk", "x": 8, "y": 13},
            {"id": "sofa", "type": "sofa", "x": 19, "y": 12, "direction": "sw"},
            {"id": "conference", "type": "meeting", "x": 16, "y": 4},
            {"id": "guardian-station", "type": "security", "x": 8, "y": 2},
            {"id": "fridge", "type": "fridge", "x": 28, "y": 20},
            {"id": "screen", "type": "screen", "x": 17, "y": 1},
            {"id": "plant-1", "type": "plant", "x": 1, "y": 2},
            {"id": "plant-2", "type": "plant", "x": 22, "y": 2},
            {"id": "plant-3", "type": "plant", "x": 13, "y": 11},
            {"id": "reading-shelf", "type": "bookcase", "x": 1, "y": 5},
            {"id": "archive-room", "type": "archive", "x": 12, "y": 1},
            {"id": "reading-lamp", "type": "lamp", "x": 13, "y": 20},
            {"id": "coffee-corner", "type": "coffee", "x": 28, "y": 18},
            {"id": "lounge-sofa", "type": "sofa", "x": 19, "y": 21, "direction": "ne"},
            {"id": "lounge-west-sofa", "type": "sofa", "x": 15, "y": 16, "direction": "se"},
            {"id": "lounge-east-sofa", "type": "sofa", "x": 25, "y": 16, "direction": "nw"},
            {"id": "lounge-tea-table", "type": "tea_table", "x": 20, "y": 16, "direction": "sw"},
            {"id": "lounge-plant", "type": "plant", "x": 28, "y": 23},
        ],
    }


def anchors(room: dict[str, Any]) -> list[dict[str, Any]]:
    """因为方向和接触点是素材能力的一部分，需要从统一目录派生座位，而非逐类硬编码。"""
    # 1、保留旧主座位 ID；不同朝向同时改变接近位置、人物朝向与座面接触。
    result = []
    for obj in room["objects"]:
        result.extend(interaction_anchors(obj))
        if obj["id"] == "guardian-station" and obj["type"] == "cabinet":
            width, depth = footprint(obj)
            point = [obj["x"] + width, obj["y"] + depth]
            result.append(
                {
                    "id": obj["id"],
                    "object_id": obj["id"],
                    "approach": point,
                    "position": [value + 0.5 for value in point],
                    "posture": "standing",
                }
            )
    # 2、地面目标保持整数索引和格心位置，不借用任何执行状态。
    for x in range(2, room["width"] - 1, 2):
        result.append(
            {
                "id": f"floor-{x}",
                "object_id": None,
                "approach": [x, room["height"] - 1],
                "position": [x + 0.5, room["height"] - 0.5],
                "posture": "standing",
            }
        )
    return result


def path_to(room: dict[str, Any], start: list[int], end: list[int]) -> list[list[int]]:
    """因为直接插值会穿过家具，需要在有界格网使用四邻域 A* 查找实际可走的路段。"""
    # 1、只用可信家具占地构造障碍，不允许模型下发世界坐标或路径脚本。
    blocked = {
        (obj["x"] + dx, obj["y"] + dy)
        for obj in room["objects"]
        for dx in range(footprint(obj)[0])
        for dy in range(footprint(obj)[1])
    }
    origin, target = tuple(start), tuple(end)
    # 2、空椅也有实体，路线不能穿过其他坐席；起终点仅允许本次离座和入座。
    chair_cells = {
        tuple(anchor["approach"]) for anchor in anchors(room) if anchor["posture"] == "seated"
    }
    blocked.update(chair_cells - {origin, target})
    if origin in blocked or target in blocked:
        raise ValueError("目标接近点被家具阻挡")
    queue = [(0, origin)]
    costs = {origin: 0}
    previous: dict[tuple[int, ...], tuple[int, ...]] = {}
    # 3、固定画布限制搜索规模；找不到路时保持原姿态并用文字反馈。
    while queue:
        _, cell = heapq.heappop(queue)
        if cell == target:
            route = [list(cell)]
            while cell in previous:
                cell = previous[cell]
                route.append(list(cell))
            return route[::-1]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            next_cell = (cell[0] + dx, cell[1] + dy)
            if (
                not 0 <= next_cell[0] < room["width"]
                or not 0 <= next_cell[1] < room["height"]
                or next_cell in blocked
            ):
                continue
            score = costs[cell] + 1
            if score < costs.get(next_cell, 100000):
                costs[next_cell], previous[next_cell] = score, cell
                heapq.heappush(
                    queue,
                    (
                        score + abs(next_cell[0] - target[0]) + abs(next_cell[1] - target[1]),
                        next_cell,
                    ),
                )
    raise ValueError("没有可达路径，未移动人物")


class SceneStore:
    def __init__(self, path: Path) -> None:
        """因为布局和人物位置不属于账号执行配置，需要在独立本机场景库持久化。"""
        # 1、场景事务不与 Agent 轨迹事务绑定，也不决定任何工具许可。
        self.db = sqlite3.connect(path, timeout=0.1)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS room(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS placements(member_id TEXT PRIMARY KEY, body TEXT NOT NULL);
        """)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO room VALUES(1,?)", (json.dumps(default_room()),))
        self._migrate_reception()
        self._migrate_office_template()
        self._migrate_lounge()
        self._migrate_archive()
        self._migrate_chair_clearance()

    def _migrate_chair_clearance(self) -> None:
        """因为旧默认盆栽紧邻第四工位的拉椅区，需要仅为完全匹配的旧模板留出离座空间。"""
        # 1、完整比较家具清单和房间尺寸；任何用户新增、移动或座高修改都会保留原布局。
        room = json.loads(self.db.execute("SELECT body FROM room WHERE id=1").fetchone()[0])
        updated = default_room()
        previous = json.loads(json.dumps(updated))
        next(obj for obj in previous["objects"] if obj["id"] == "plant-3")["y"] = 13
        if (room["width"], room["height"], room["objects"]) != (
            previous["width"],
            previous["height"],
            previous["objects"],
        ):
            return
        # 2、不变更人物锚点与执行记录，仅提交桌面布局的新版本。
        updated["revision"] = room["revision"] + 1
        with self.db:
            self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(updated),))

    def _migrate_office_template(self) -> None:
        """因为旧默认工位和基础设施散落，需要仅升级未经用户改动的模板，并保持人物锚点身份。

        自定义家具、已移动模板或未知布局保持原样；只更新桌面场景，不修改 Agent 与会话。
        """
        # 1、按原默认家具的完整坐标与类型识别，不能只凭 revision 覆盖用户布置。
        room = json.loads(self.db.execute("SELECT body FROM room WHERE id=1").fetchone()[0])
        expected = {
            "reception-desk": ("desk", 3, 2),
            "desk-1": ("desk", 3, 8),
            "desk-2": ("desk", 8, 8),
            "desk-3": ("desk", 8, 13),
            "sofa": ("sofa", 2, 15),
            "conference": ("meeting", 16, 3),
            "guardian-station": ("cabinet", 19, 14),
            "fridge": ("fridge", 21, 10),
            "screen": ("screen", 16, 1),
            "plant-1": ("plant", 1, 2),
            "plant-2": ("plant", 22, 2),
            "plant-3": ("plant", 14, 15),
            "reading-shelf": ("bookcase", 1, 11),
            "reading-lamp": ("lamp", 1, 17),
            "coffee-corner": ("coffee", 22, 13),
            "lounge-sofa": ("sofa", 16, 16),
            "lounge-plant": ("plant", 22, 17),
        }
        objects = {
            obj["id"]: (obj["type"], obj["x"], obj["y"])
            for obj in room["objects"]
            if obj["type"] != "archive"
        }
        if room["width"] != 24 or room["height"] != 19 or objects != expected:
            return
        archives = [obj for obj in room["objects"] if obj["type"] == "archive"]
        if len(archives) > 1 or any(
            (obj["x"], obj["y"]) not in {(11, 1), (20, 1)} for obj in archives
        ):
            return
        # 2、保留原档案入口 ID 与所有人物目标，两张沙发统一收拢到同一休闲区。
        updated = default_room()
        updated["revision"] = room["revision"] + 1
        archive = next((obj for obj in room["objects"] if obj["type"] == "archive"), None)
        if archive:
            next(obj for obj in updated["objects"] if obj["type"] == "archive")["id"] = archive[
                "id"
            ]
        for anchor in anchors(updated):
            path_to(updated, [0, 0], anchor["approach"])
        with self.db:
            self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(updated),))
            for member, body in self.db.execute("SELECT * FROM placements").fetchall():
                placement = json.loads(body)
                placement["generation"] += 1
                self.db.execute(
                    "UPDATE placements SET body=? WHERE member_id=?",
                    (json.dumps(placement), member),
                )

    def _migrate_lounge(self) -> None:
        """因为默认休闲区要升级为四张相向沙发，需要只匹配已知旧模板并保留自定义场景和座位身份。"""
        # 1、完整匹配此前标准布局，未知额外家具和人工移动都不会被覆盖。
        room = json.loads(self.db.execute("SELECT body FROM room WHERE id=1").fetchone()[0])
        expected = {
            "reception-desk": ("desk", 3, 2),
            "desk-1": ("desk", 3, 8),
            "desk-2": ("desk", 8, 8),
            "desk-3": ("desk", 3, 13),
            "desk-4": ("desk", 8, 13),
            "sofa": ("sofa", 16, 12),
            "conference": ("meeting", 16, 4),
            "guardian-station": ("security", 8, 2),
            "fridge": ("fridge", 22, 15),
            "screen": ("screen", 17, 1),
            "plant-1": ("plant", 1, 2),
            "plant-2": ("plant", 22, 2),
            "plant-3": ("plant", 13, 13),
            "reading-shelf": ("bookcase", 1, 5),
            "reading-lamp": ("lamp", 15, 16),
            "coffee-corner": ("coffee", 22, 13),
            "lounge-sofa": ("sofa", 16, 16),
            "lounge-plant": ("plant", 22, 17),
        }
        actual = {
            obj["id"]: (obj["type"], obj["x"], obj["y"])
            for obj in room["objects"]
            if obj["type"] != "archive"
        }
        archives = [obj for obj in room["objects"] if obj["type"] == "archive"]
        if len(archives) > 1 or any((obj["x"], obj["y"]) != (12, 1) for obj in archives):
            return
        if (
            room["width"] != 24
            or room["height"] != 19
            or actual != expected
            or any("direction" in obj for obj in room["objects"])
        ):
            return
        # 2、新模板先验证全部交互点可达，保留档案室 ID 与成员原锚点引用。
        updated = default_room()
        updated["revision"] = room["revision"] + 1
        archive = next((obj for obj in room["objects"] if obj["type"] == "archive"), None)
        if archive:
            next(obj for obj in updated["objects"] if obj["type"] == "archive")["id"] = archive[
                "id"
            ]
        for anchor in anchors(updated):
            path_to(updated, [0, 0], anchor["approach"])
        with self.db:
            self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(updated),))
            for member, body in self.db.execute("SELECT * FROM placements").fetchall():
                placement = json.loads(body)
                placement["generation"] += 1
                self.db.execute(
                    "UPDATE placements SET body=? WHERE member_id=?",
                    (json.dumps(placement), member),
                )

    def _migrate_archive(self) -> None:
        """因为已有会议室也需要档案室入口，需要在空闲墙边补充设施并保留用户所有原位置。"""
        # 1、已有档案设施不重复创建，满房间保留侧栏入口，不强制移动或删除用户家具。
        room = json.loads(self.db.execute("SELECT body FROM room WHERE id=1").fetchone()[0])
        if any(obj["type"] == "archive" for obj in room["objects"]):
            return
        occupied = {
            (obj["x"] + dx, obj["y"] + dy)
            for obj in room["objects"]
            for dx in range(footprint(obj)[0])
            for dy in range(footprint(obj)[1])
        }
        for x in range(room["width"] - 4, 1, -1):
            if {(x, 1), (x + 1, 1)} & occupied:
                continue
            # 2、新设施只有展示与打开说明的能力，布局版本更新不改变任何任务或记忆。
            identifier = "archive-" + uuid4().hex[:8]
            room["objects"].append({"id": identifier, "type": "archive", "x": x, "y": 1})
            room["revision"] += 1
            with self.db:
                self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(room),))
            return

    def _migrate_reception(self) -> None:
        """因为旧布局保留老板工位名称，需要只迁移接待台标识而保留家具坐标及用户布置。"""
        # 1、角色记录保留用于历史追溯，场景旧老板占位释放，其他成员座位不强制改变。
        room = json.loads(self.db.execute("SELECT body FROM room WHERE id=1").fetchone()[0])
        if not any(obj["id"] == "boss-desk" for obj in room["objects"]):
            return
        with self.db:
            for obj in room["objects"]:
                if obj["id"] == "boss-desk":
                    obj["id"] = "reception-desk"
            room["revision"] += 1
            self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(room),))
            self.db.execute("DELETE FROM placements WHERE member_id='boss'")
            for member_id, body in self.db.execute("SELECT * FROM placements").fetchall():
                place = json.loads(body)
                if place["anchor_id"].startswith("boss-desk"):
                    place["anchor_id"] = place["anchor_id"].replace(
                        "boss-desk", "reception-desk", 1
                    )
                    place["generation"] += 1
                    self.db.execute(
                        "UPDATE placements SET body=? WHERE member_id=?",
                        (json.dumps(place), member_id),
                    )

    def snapshot(self, members: list[dict[str, Any]]) -> dict[str, Any]:
        """因为场景重连需要合法稳定状态，需要为新人物分配未占用锚点并返回快照。"""
        # 1、系统角色有固定初始锚点，员工使用实际空工位，不抢占已有座位。
        room = json.loads(self.db.execute("SELECT body FROM room WHERE id=1").fetchone()[0])
        current = {
            row[0]: json.loads(row[1]) for row in self.db.execute("SELECT * FROM placements")
        }
        if members:
            live = {member["id"] for member in members}
            with self.db:
                for stale in set(current) - live:
                    self.db.execute("DELETE FROM placements WHERE member_id=?", (stale,))
                    del current[stale]
        occupied = {value["anchor_id"] for value in current.values()}
        candidates = anchors(room)
        work_ids = {obj["id"] for obj in room["objects"] if obj["type"] == "desk"}
        ordered = (
            [value for value in candidates if value["id"] in work_ids]
            + [value for value in candidates if value["object_id"] is None]
            + [
                value
                for value in candidates
                if value["id"] not in work_ids and value["object_id"] is not None
            ]
        )
        for member in members:
            if member["id"] not in current:
                preferred = {
                    "assistant": "reception-desk",
                    "guardian": "guardian-station",
                }.get(member["id"])
                available = next(
                    (anchor["id"] for anchor in ordered if anchor["id"] not in occupied), None
                )
                anchor_id = (
                    preferred
                    if preferred
                    and preferred not in occupied
                    and any(anchor["id"] == preferred for anchor in candidates)
                    else available
                )
                if anchor_id:
                    placement = {"member_id": member["id"], "anchor_id": anchor_id, "generation": 1}
                    with self.db:
                        self.db.execute(
                            "INSERT INTO placements VALUES(?,?)",
                            (member["id"], json.dumps(placement)),
                        )
                    current[member["id"]], occupied = placement, occupied | {anchor_id}
        return {
            "room": {
                **room,
                "objects": [
                    {**obj, "direction": object_direction(obj), "footprint": list(footprint(obj))}
                    for obj in room["objects"]
                ],
            },
            "anchors": anchors(room),
            "asset_contract": {"version": 1, "definitions": scene_catalog()["definitions"]},
            "placements": list(current.values()),
            "catalog": {key: list(value) for key, value in CATALOG.items()},
            "navigation": navigation_map(room),
        }

    def move(
        self, member_id: str, anchor_id: str, revision: int, start: list[int] | None = None
    ) -> dict[str, Any]:
        """因为两个角色不能同时占用一席，需要验证场景版本和占座后生成独立表现移动计划。"""
        # 1、该命令只改变人物的显示目标，不启动、停止或批准任何工作。
        snapshot = self.snapshot([])
        room = snapshot["room"]
        if room["revision"] != revision:
            raise ValueError("布局已变化，请刷新后重试")
        target = next((anchor for anchor in snapshot["anchors"] if anchor["id"] == anchor_id), None)
        source = next(
            (place for place in snapshot["placements"] if place["member_id"] == member_id), None
        )
        if target is None or source is None:
            raise ValueError("人物或锚点不存在")
        if any(
            place["member_id"] != member_id and place["anchor_id"] == anchor_id
            for place in snapshot["placements"]
        ):
            raise ValueError("该座位已被其他成员占用")
        origin = next(
            anchor for anchor in snapshot["anchors"] if anchor["id"] == source["anchor_id"]
        )
        if start is not None and (
            not isinstance(start, list)
            or len(start) != 2
            or any(type(value) is not int for value in start)
            or not 0 <= start[0] < room["width"]
            or not 0 <= start[1] < room["height"]
        ):
            raise ValueError("显示起点必须是画布内的整数格")
        route = path_to(
            room, start if start is not None else origin["approach"], target["approach"]
        )
        # 2、保存逻辑目标，前端先站稳再移动；重连直接恢复稳定目标，不重播历史行走。
        saved = {
            "member_id": member_id,
            "anchor_id": anchor_id,
            "generation": source["generation"] + 1,
        }
        with self.db:
            self.db.execute(
                "UPDATE placements SET body=? WHERE member_id=?", (json.dumps(saved), member_id)
            )
        return {
            "plan_id": uuid4().hex,
            **saved,
            "scene_revision": revision,
            "route": route,
            "target": target,
            "source": origin,
            "mode": "presentation_only",
        }

    def edit(self, values: dict[str, Any], revision: int) -> dict[str, Any]:
        """因为固定画布允许布置但不能越界重叠，需要校验统一家具约束并使用版本比较更新。"""
        # 1、不能移动已被占座的家具；人物先离开，再修改其锚点。
        snapshot = self.snapshot([])
        room = snapshot["room"]
        if room["revision"] != revision:
            raise ValueError("布局已被修改，请刷新")
        identifier = str(values.get("id") or uuid4().hex)
        existing = next((obj for obj in room["objects"] if obj["id"] == identifier), None)
        occupied_ids = {place["anchor_id"] for place in snapshot["placements"]}
        occupied_objects = {
            anchor["object_id"] for anchor in snapshot["anchors"] if anchor["id"] in occupied_ids
        }
        if existing and identifier in occupied_objects:
            raise ValueError("请先让人物离开该家具")
        kind = str(values.get("type", existing["type"] if existing else "plant"))
        if kind not in CATALOG:
            raise ValueError("未知家具类型")
        if set(values) - {"id", "type", "x", "y", "direction", "seat_height", "remove"}:
            raise ValueError("布局字段不受支持")
        if values.get("remove"):
            if existing is None:
                raise ValueError("家具不存在")
            updated = {
                **room,
                "revision": revision + 1,
                "objects": [obj for obj in room["objects"] if obj["id"] != identifier],
            }
            for anchor in anchors(updated):
                path_to(updated, [0, 0], anchor["approach"])
            with self.db:
                self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(updated),))
            return updated
        if any(type(values.get(key)) is not int for key in ("x", "y")):
            raise ValueError("家具位置必须是整数格网坐标")
        x, y = values["x"], values["y"]
        if existing is None and len(room["objects"]) >= 64:
            raise ValueError("首版每个房间最多 64 件家具")
        direction = (
            values.get("direction", existing.get("direction") if existing else None)
            or scene_catalog()["definitions"][kind]["default_direction"]
        )
        if direction not in DIRECTIONS:
            raise ValueError("家具方向必须是八方向之一")
        seat_height = values.get("seat_height", existing.get("seat_height", 22) if existing else 22)
        if type(seat_height) is not int or not 12 <= seat_height <= 32:
            raise ValueError("座面高度需要是 12～32 的整数")
        candidate = {
            "id": identifier,
            "type": kind,
            "x": x,
            "y": y,
            "direction": direction,
            "seat_height": seat_height,
        }
        width, height = footprint(candidate)
        if x < 1 or y < 1 or x + width >= room["width"] or y + height >= room["height"]:
            raise ValueError("家具超出固定画布")
        for obj in room["objects"]:
            other_w, other_h = footprint(obj)
            if (
                obj["id"] != identifier
                and x < obj["x"] + other_w
                and x + width > obj["x"]
                and y < obj["y"] + other_h
                and y + height > obj["y"]
            ):
                raise ValueError("家具占地重叠")
        # 2、所有已有锚点仍需可达，避免一次布局编辑把人员封死。
        updated = {
            **room,
            "revision": revision + 1,
            "objects": [obj for obj in room["objects"] if obj["id"] != identifier] + [candidate],
        }
        candidate_anchors = anchors(updated)
        for anchor in candidate_anchors:
            path_to(updated, [0, 0], anchor["approach"])
        with self.db:
            self.db.execute("UPDATE room SET body=? WHERE id=1", (json.dumps(updated),))
        return updated

    def close(self) -> None:
        """因为场景库有自己的连接，需要在退出时独立释放。"""
        # 1、不影响账号元数据和工作日志。
        self.db.close()


def navigation_map(room: dict[str, Any]) -> dict[str, Any]:
    """因为空闲散步与开会只改变表现，需要公开有限障碍网格供本地视觉路线复用。

    不包含任务、工具或文件权限；图形导航不调用执行器或持久化人物目的地。
    """
    # 1、障碍仍以服务端家具目录的真实占地为准，最多固定房间格数。
    blocked = sorted(
        {
            (obj["x"] + dx, obj["y"] + dy)
            for obj in room["objects"]
            for dx in range(footprint(obj)[0])
            for dy in range(footprint(obj)[1])
        }
    )
    return {
        "version": 1,
        "revision": room["revision"],
        "width": room["width"],
        "height": room["height"],
        "blocked": [list(point) for point in blocked],
        "seats": [anchor["approach"] for anchor in anchors(room) if anchor["posture"] == "seated"],
    }
