/* 同任务会议导演：仅消费真实关系，不创建或阻塞子 Agent。 */
"use strict";

class CrewCollaborationDirector {
    /** 因为协作动作必须与生活和人工移动仲裁，需要独立维护会议座位与本地接管冷却。 */
    constructor(motion, navigator) {
        // 1、无桌面桥和业务状态写入，关系随快照重建。
        this.motion = motion;
        this.navigator = navigator;
        this.assignments = new Map();
        this.hints = new Map();
        this.blocked = new Map();
        this.participants = new Set();
        this.retryAt = new Map();
    }

    /** 因为用户手动换座不能立即被旧会议覆盖，需要暂时让出该人物的空间控制。 */
    engage(identifier, now) {
        // 1、只暂停表现，不退出实际委派或取消任何任务。
        this.blocked.set(identifier, now + 300000);
        this.assignments.delete(identifier);
        this.hints.delete(identifier);
    }

    /** 因为隐藏和降级后不能补播旧会议，需要释放临时关系并恢复逻辑锚点。 */
    clear() {
        // 1、恢复只影响插值，当前 Run 由后端继续执行。
        for (const id of this.assignments.keys())
            this.motion.returnVisual(id, this.navigator);
        this.assignments.clear();
        this.hints.clear();
        this.participants.clear();
    }

    /** 因为多个配置成员的同一任务要聚在一起，需要按真实 Run 分配会议点并呈现讨论。 */
    tick(groups, scene, views, facts, healthy, now) {
        // 1、优先确定可见参与关系，人工和报错始终显示本身的真实状态。
        this.hints.clear();
        this.participants.clear();
        const wanted = new Map();
        if (healthy)
            for (const group of groups || []) {
                if (group.kind !== "meeting" || !Array.isArray(group.members))
                    continue;
                const members = group.members.filter(crewMeetingMember, {
                    views,
                    facts,
                    blocked: this.blocked,
                    now,
                });
                if (members.length < 2) continue;
                for (const id of members)
                    if (!wanted.has(id)) {
                        wanted.set(id, group.group_id);
                        this.participants.add(id);
                    }
            }
        for (const [id, old] of this.assignments)
            if (wanted.get(id) !== old.group) {
                if (this.motion.actors.get(id)?.visualKind === "meeting")
                    this.motion.returnVisual(id, this.navigator);
                this.assignments.delete(id);
            }
        // 2、只借用没有被其他人物占据的会议锚点；不足时在会议桌旁空地站立讨论。
        const meetingObjects = new Set(
            (scene?.room.objects || [])
                .filter(crewMeetingObject)
                .map(crewObjectIdentity),
        );
        const registeredSeats = (scene?.anchors || []).filter(
            crewMeetingAnchor,
            meetingObjects,
        );
        const seats = [];
        // 3、优先使用相对座点，给高细节人物留出社交距离，避免两人挤在同一桌边。
        for (let parity = 0; parity < 2; parity++)
            for (let index = parity; index < registeredSeats.length; index += 2)
                seats.push(registeredSeats[index]);
        const used = new Set();
        for (const [id, assignment] of this.assignments)
            if (wanted.has(id)) used.add(assignment.anchor.id);
        for (const [id, group] of wanted) {
            const actor = this.motion.actors.get(id);
            if (!actor) continue;
            let assignment = this.assignments.get(id);
            if (
                assignment &&
                (assignment.revision !== this.navigator.revision ||
                    assignment.generation !== actor.generation)
            ) {
                this.assignments.delete(id);
                assignment = null;
            }
            if (!assignment) {
                if (now < (this.retryAt.get(id) || 0)) continue;
                let anchor = null;
                for (const seat of seats) {
                    const occupied = (scene.placements || []).some(
                        crewSeatOccupied,
                        { seat: seat.id, id, wanted },
                    );
                    if (!used.has(seat.id) && !occupied) {
                        anchor = {
                            ...seat,
                            posture: "standing",
                            position: [...seat.approach],
                        };
                        break;
                    }
                }
                if (!anchor && seats.length) {
                    const nearby = this.navigator.nearby(
                        seats[0].approach,
                        used,
                    );
                    for (const point of nearby) {
                        if (!used.has(point.join(","))) {
                            anchor = {
                                id: point.join(","),
                                position: point,
                                approach: point,
                                posture: "standing",
                            };
                            break;
                        }
                    }
                }
                if (!anchor) {
                    this.retryAt.set(id, now + 2000);
                    continue;
                }
                const route = this.navigator.route(
                    actor.groundCell,
                    anchor.approach,
                );
                if (!route.length) {
                    this.retryAt.set(id, now + 2000);
                    continue;
                }
                this.motion.visualMove(id, route, anchor, "meeting");
                assignment = {
                    group,
                    anchor,
                    generation: actor.generation,
                    revision: this.navigator.revision,
                };
                this.assignments.set(id, assignment);
                used.add(anchor.id);
            }
            const settled = actor.phase === "settled",
                index = [...wanted.keys()].indexOf(id);
            this.hints.set(id, {
                kind: "meeting",
                activity: "meeting",
                action:
                    (Math.floor(now / 3500) + index) % 2 ? "listen" : "talk",
                caption: settled ? "协作 · 同一任务讨论" : "协作 · 前往会议区",
                groupId: group,
            });
        }
    }
}

/** 因为疑问和报错不能被会议掩盖，需要筛选真实可参与且未被人工接管的人物。 */
function crewMeetingMember(id) {
    // 1、身份来自已配置成员，不为外援创建形象。
    const member = this.views.get(id)?.member,
        fact = this.facts.get(id);
    return (
        member &&
        ["assistant", "employee"].includes(member.role) &&
        member.enabled &&
        !fact?.question_count &&
        !fact?.warning_count &&
        (this.blocked.get(id) || 0) <= this.now
    );
}
/** 因为会议区可以由用户布置，需要只识别统一目录中的会议桌。 */
function crewMeetingObject(object) {
    // 1、不依赖家具显示名称。
    return object.type === "meeting";
}
/** 因为会议锚点需要按所属家具归类，需要读取稳定对象 ID。 */
function crewObjectIdentity(object) {
    // 1、返回普通字符串，不创建资源路径。
    return object.id;
}
/** 因为不同会议桌可有各自座位，需要按服务端锚点关系筛选。 */
function crewMeetingAnchor(anchor) {
    // 1、只使用原合同已有的可接近点。
    return this.has(anchor.object_id) && anchor.posture === "seated";
}
/** 因为临时会议不能抢占用户安排的其他人物，需要检查持久化座位归属。 */
function crewSeatOccupied(place) {
    // 1、同一任务成员可以继续使用本人的座位，其他人物的座位保持保留。
    return place.anchor_id === this.seat && place.member_id !== this.id;
}
