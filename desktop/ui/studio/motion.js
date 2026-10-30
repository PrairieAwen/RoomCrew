/* 空间插值状态机：不决定任务状态，只消费已验证的格网路线。 */
"use strict";

class CrewMotion {
    /** 因为人物可以复用 Agent 而位置必须独立，需要按 member ID 维护显示状态。 */
    constructor() {
        // 1、任何移动状态均可从持久化目标恢复，不回调执行器。
        this.actors = new Map();
        this.chairs = new Map();
        this.presetMembers = new Map();
    }

    /** 因为重连不应重播历史走动，需要直接恢复到稳定目标与合法姿态。 */
    restore(placement, anchors, revision) {
        // 1、在途同代次保持原插值；布局变更或更新代次才重新定位。
        if (this.chairRevision !== revision) { this.chairs.clear();this.chairRevision=revision; }
        const old = this.actors.get(placement.member_id);
        if (old) {
            old.chairPreset = this.presetMembers.has(placement.member_id);
            old.chairFoot = this.presetMembers.get(placement.member_id);
        }
        if (
            old &&
            old.generation >= placement.generation &&
            old.revision === revision
        )
            return;
        const target = anchors.find(crewAnchorMatches, placement.anchor_id);
        if (!target) return;
        this.actors.set(placement.member_id, {
            generation: placement.generation,
            chairPreset: this.presetMembers.has(placement.member_id),
            chairFoot: this.presetMembers.get(placement.member_id),
            revision,
            position: [...target.position],
            groundCell: [...target.approach],
            posture: target.posture,
            target,
            route: [],
            elapsed: 0,
            phase: "settled",
            progress: 1,
            direction: target.direction || "se",
            gait: "walk",
        });
    }

    /** 因为快速改目的地和起坐都不能造成瞬移，需要从当前可见位置开始分阶段执行新计划。 */
    accept(plan) {
        // 1、拒绝旧布局、旧代次与重复计划，所有坐标仍来自后端验证路线。
        const old = this.actors.get(plan.member_id);
        if (
            old &&
            (old.revision > plan.scene_revision ||
                (old.revision === plan.scene_revision &&
                    (old.generation > plan.generation ||
                        (old.generation === plan.generation && old.planId))))
        )
            return false;
        if (
            plan.mode !== "presentation_only" ||
            !Array.isArray(plan.route) ||
            !plan.route.length
        )
            return false;
        const snapshotFirst = old && old.generation === plan.generation;
        const leaving = !snapshotFirst && old && ["seat_turn", "stand_up"].includes(old.phase);
        const seated = snapshotFirst
            ? plan.source?.posture === "seated"
            : old?.posture === "seated" || old?.phase === "sit_down";
        const position = snapshotFirst
            ? plan.source.position
            : old?.position || plan.source?.position || plan.route[0];
        // 2、起身和行走分开；站着改路线时接回地面格，不传送到上次逻辑目标。
        this.actors.set(plan.member_id, {
            generation: plan.generation,
            chairPreset: this.presetMembers.has(plan.member_id),
            chairFoot: this.presetMembers.get(plan.member_id),
            revision: plan.scene_revision,
            planId: plan.plan_id,
            manual: plan.manual === true,
            position: [...position],
            groundCell: [...plan.route[0]],
            posture: "standing",
            target: plan.target,
            sourceSeat: seated ? (snapshotFirst ? plan.source : old?.sourceSeat || old?.target || plan.source) : null,
            route: plan.route.map(crewCopyPoint),
            elapsed: 0,
            direction:
                old?.visualDirection ||
                old?.direction ||
                plan.source?.direction ||
                "se",
            gait: plan.gait === "run" ? "run" : "walk",
            phase: seated ? "stand_up" : "moving",
            progress: 0,
            from: [...position],
            approach: crewCellCenter(plan.route[0]),
            seatMix: seated ? 1 : 0,
        });
        // 3、离座中再次点击只替换后续路线，保留原椅、姿势和进度，不能坐回去或直接跳成步行。
        const actor = this.actors.get(plan.member_id);
        if (leaving) {
            for (const key of ["phase", "progress", "seatMix", "poseProgress", "sourceSeat",
                "chairExit", "departureFrom", "approach", "from", "turnFrom", "exitDirection", "direction"])
                actor[key] = old[key];
        } else if (seated) this.beginDeparture(actor);
        return true;
    }

    /** 因为转向用户后的椅子不能直接跳成背面起身，需要先旋转座椅再沿配套动作离座。 */
    beginDeparture(actor) {
        // 1、只标准椅使用配套片段，自制椅和沙发保留通用起坐。
        if (!crewStandardChair(actor.sourceSeat, actor)) return;
        actor.exitDirection=crewSeatBackDirection(actor.direction);
        actor.departureFrom=[...actor.position];
        actor.chairExit=crewSeatExit(actor.sourceSeat,actor.exitDirection, actor);
        if (actor.direction!==actor.exitDirection) {
            actor.phase="seat_turn";actor.turnFrom=actor.direction;actor.progress=0;actor.seatMix=1;
        }
    }

    /** 因为长帧不能穿过家具或跳过起坐，需要限制时间步并只推进当前动作阶段。 */
    step(seconds) {
        // 1、动画时钟不驱动 Agent；暂停页面后允许直接恢复稳定显示目标。
        const dt = Math.min(0.05, Math.max(0, seconds));
        for (const actor of this.actors.values()) {
            if (actor.interactionHold && actor.phase === "moving") continue;
            actor.elapsed += dt;
            if (["seat_turn","seat_turn_in"].includes(actor.phase)) {
                actor.progress=Math.min(1,actor.progress+dt/0.4);
                const desired=actor.phase==="seat_turn"?actor.exitDirection:actor.target.direction;
                actor.direction=crewTurnDirection(actor.turnFrom,desired,crewEase(actor.progress));
                if(actor.progress===1) {
                    actor.direction=desired;
                    actor.phase=actor.phase==="seat_turn"?"stand_up":"settled";
                    actor.progress=actor.phase==="settled"?1:0;
                }
                continue;
            }
            if (actor.phase === "turn_to_seat") {
                actor.progress = Math.min(1, actor.progress + dt / 0.38);
                const from = CREW_DIRECTIONS.indexOf(
                    actor.turnFrom || actor.direction,
                );
                const to = CREW_DIRECTIONS.indexOf(
                    (crewStandardChair(actor.target, actor)?crewSeatBackDirection(actor.target.direction):actor.target.direction) || "se",
                );
                const delta = ((to - from + 12) % 8) - 4;
                actor.direction =
                    CREW_DIRECTIONS[
                        (Math.round(from + delta * crewEase(actor.progress)) +
                            8) %
                            8
                    ];
                if(crewStandardChair(actor.target, actor)) {
                    actor.chairExit ||= crewSeatExit(actor.target,crewSeatBackDirection(actor.target.direction), actor);
                    actor.chairStart ||= [...(this.chairs.get(actor.target.id)||actor.target.position)];
                    this.chairs.set(actor.target.id,crewLerpPoint(actor.chairStart,actor.chairExit,crewEase(actor.progress)));
                }
                if (actor.progress === 1) {
                    actor.direction = crewStandardChair(actor.target, actor)?crewSeatBackDirection(actor.target.direction):actor.target.direction || "se";
                    actor.phase = "sit_down";
                    actor.progress = 0;
                    actor.from = [...actor.position];
                    if(crewStandardChair(actor.target, actor)) actor.position=[...actor.chairExit];
                }
                continue;
            }
            if (actor.phase === "stand_up") {
                actor.progress = Math.min(1, actor.progress + dt / 0.75);
                if(crewStandardChair(actor.sourceSeat, actor)) {
                    actor.chairExit ||= crewSeatExit(actor.sourceSeat,actor.direction, actor);
                    actor.position=crewLerpPoint(actor.departureFrom||actor.from,actor.chairExit,crewEase(Math.min(1,actor.progress/0.3)));
                    actor.poseProgress=Math.max(0,(actor.progress-0.3)/0.7);
                    this.chairs.set(actor.sourceSeat.id,[...actor.position]);
                    actor.seatMix=1-crewEase(actor.poseProgress);
                    if(actor.progress===1) {actor.position=[...actor.approach];actor.phase="moving";actor.sourceSeat=null;}
                    continue;
                }
                actor.position = crewLerpPoint(
                    actor.from,
                    actor.approach,
                    crewEase(Math.max(0, (actor.progress - 0.5) * 2)),
                );
                actor.seatMix = 1 - crewEase(actor.progress);
                if (actor.progress === 1) {
                    actor.phase = "moving";
                    actor.sourceSeat = null;
                }
                continue;
            }
            if (actor.phase === "sit_down") {
                actor.progress = Math.min(1, actor.progress + dt / 0.85);
                if(crewStandardChair(actor.target, actor)) {
                    actor.poseProgress=1-Math.min(1,actor.progress/0.7);
                    actor.position=crewLerpPoint(actor.chairExit,actor.target.position,crewEase(Math.max(0,(actor.progress-0.7)/0.3)));
                    this.chairs.set(actor.target.id,[...actor.position]);
                } else actor.position = crewLerpPoint(
                    actor.from,
                    actor.target.position,
                    crewEase(Math.min(1, actor.progress * 2)),
                );
                actor.seatMix = crewEase(actor.progress);
                if (actor.progress === 1) {
                    actor.phase = "settled";
                    actor.posture = "seated";
                    if(crewStandardChair(actor.target, actor)&&actor.direction!==actor.target.direction) {
                        actor.phase="seat_turn_in";actor.turnFrom=actor.direction;actor.progress=0;
                    }
                    if (actor.visualKind === "return") {
                        delete actor.visualHome;
                        delete actor.visualKind;
                    }
                }
                continue;
            }
            if (actor.phase !== "moving") continue;
            // 2、速度按世界格计算；方向按投影后的真实移动向量决定，不直接旋转平面人物。
            const cell = actor.route[0];
            if (!cell) {
                this.arrive(actor);
                continue;
            }
            const next = crewCellCenter(cell);
            const dx = next[0] - actor.position[0],
                dy = next[1] - actor.position[1],
                distance = Math.hypot(dx, dy);
            const speed = actor.gait === "run" ? 5.4 : 2.8;
            if (distance > 0.001) actor.direction = crewDirection([dx, dy]);
            if (distance <= dt * speed) {
                actor.position = [...next];
                actor.groundCell = [...cell];
                actor.route.shift();
            } else {
                actor.position[0] += (dx / distance) * dt * speed;
                actor.position[1] += (dy / distance) * dt * speed;
            }
            if (!actor.route.length) this.arrive(actor);
        }
    }

    /** 因为到达接近点不等于已经坐下，需要明确开始落座过渡或确认站立目标。 */
    arrive(actor) {
        // 1、落座只影响表现，事件轨迹与工具状态都不在这个阶段里修改。
        delete actor.chairExit;
        delete actor.chairStart;
        actor.poseProgress = 1;
        if (actor.target.posture === "seated") {
            actor.turnFrom = actor.direction;
            actor.phase = "turn_to_seat";
            actor.progress = 0;
            actor.from = [...actor.position];
            actor.seatMix = 0;
        } else {
            actor.phase = "settled";
            actor.position = [...actor.target.position];
            actor.posture = "standing";
            actor.seatMix = 0;
        }
        if (actor.phase === "settled" && actor.visualKind === "return") {
            delete actor.visualHome;
            delete actor.visualKind;
        }
    }

    /** 因为散步与会议不该占用持久化座位，需要在同一插值器里执行可随时丢弃的显示路线。 */
    visualMove(identifier, route, target, kind) {
        // 1、调用方只提供导航器验证的有限路线，真实代次、计划 ID 与逻辑座位保持不变。
        const actor = this.actors.get(identifier);
        if (
            !actor ||
            !route.length ||
            !["leisure", "meeting", "work", "return", "performance"].includes(kind)
        )
            return false;
        const seated = actor.posture === "seated" || actor.phase === "sit_down";
        actor.direction = actor.visualDirection || actor.direction;
        actor.visualHome ||= actor.target;
        actor.visualKind = kind;
        actor.from = [...actor.position];
        actor.approach = crewCellCenter(route[0]);
        actor.route = route.map(crewCopyPoint);
        actor.sourceSeat = seated ? actor.sourceSeat || actor.target : null;
        actor.target = target.posture === "standing"
            ? { ...target, position: crewCellCenter(target.approach) }
            : target;
        actor.posture = "standing";
        actor.phase = seated ? "stand_up" : "moving";
        actor.progress = 0;
        actor.seatMix = seated ? 1 : 0;
        actor.gait = kind === "meeting" ? "run" : "walk";
        if(seated) this.beginDeparture(actor);
        return true;
    }

    /** 因为工作或人工接管必须中止生活表演，需要沿地图返回原逻辑锚点而不写后端。 */
    returnVisual(identifier, navigator) {
        // 1、已在返回或没有临时移动时不重复规划；新真实计划会自然替换这些字段。
        const actor = this.actors.get(identifier);
        if (!actor?.visualHome || actor.visualKind === "return") return;
        const home = actor.visualHome;
        const route = navigator.route(actor.groundCell, home.approach);
        if (route.length) this.visualMove(identifier, route, home, "return");
        else this.settleActor(actor);
    }

    /** 因为隐藏、地图失效或无路可走时需要可靠恢复，需要回到最后一次持久化锚点。 */
    settleActor(actor) {
        // 1、只恢复显示目标，不生成会话或授权事件。
        actor.target = actor.visualHome || actor.target;
        actor.sourceSeat = null;
        delete actor.visualHome;
        delete actor.visualKind;
        actor.route = [];
        actor.position = [...actor.target.position];
        actor.groundCell = [...actor.target.approach];
        actor.posture = actor.target.posture;
        actor.phase = "settled";
        actor.progress = 1;
        actor.seatMix = actor.posture === "seated" ? 1 : 0;
        actor.direction = actor.target.direction || "se";
        if(crewStandardChair(actor.target, actor)) this.chairs.set(actor.target.id,[...actor.target.position]);
    }

    /** 因为切到后台或减少动态效果时不应补播旧移动，需要落到持久化显示目标。 */
    settle() {
        // 1、清掉的只是本地插值，没有任务成功、取消或审批命令。
        for (const actor of this.actors.values()) {
            this.settleActor(actor);
        }
    }
}

/** 因为动作序列要保留自身坐标，需要复制路线点而不共享可变数组。 */
function crewCopyPoint(point) {
    // 1、返回独立坐标供插值修改。
    return [...point];
}
/** 因为导航整数表示格子的索引而不是边缘，需要把所有行走脚底统一放到格心以留出半格身体余量。 */
function crewCellCenter(point) {
    // 1、保持路线和 groundCell 的整数合同，只有实际世界坐标增加半格。
    return [point[0] + 0.5, point[1] + 0.5];
}
/** 因为起坐过程应平滑开始和结束，需要使用有界缓入缓出。 */
function crewEase(value) {
    // 1、两端速度归零，避免身体突然弹起。
    return value * value * (3 - 2 * value);
}
/** 因为接触点不同于脚底移动点，需要在显示坐标之间连续过渡。 */
function crewLerpPoint(from, to, t) {
    // 1、插值只作用于已验证端点之间的起坐距离。
    return [from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t];
}
/** 因为等距坐标的方向不同于屏幕方向，需要从投影向量选择八向朝向。 */
function crewDirection(vector) {
    // 1、角度只用于查表，不把整个人物当平面图片旋转。
    const point = crewProject(vector);
    return CREW_DIRECTIONS[
        (Math.round(Math.atan2(point[1], point[0]) / (Math.PI / 4)) + 8) % 8
    ];
}

/** 因为标准椅的交互片段需要匹配家具规格，需要明确限制用途与座高而不是给所有家具套动画。 */
function crewStandardChair(anchor, actor = null) {
    // 1、未标注座高的旧场景沿用默认规格，沙发不满足椅子合同。
    return (!actor || actor.chairPreset === true) && anchor && ["workstation","meeting","chair"].includes(anchor.purpose) &&
        (anchor.contact?.seat_height ?? 22)===22;
}

/** 因为起坐片段只原绘西北并支持对称方向，需要在座椅旋转阶段选择真实可用的背向姿势。 */
function crewSeatBackDirection(direction) {
    // 1、前向离座先自然转椅，不能给前向动作强行换背面图片。
    return ["e","ne","se"].includes(direction)?"ne":"nw";
}

/** 因为完整交互帧以椅脚为原点，需要让最终人物脚点对准导航起点，避免接回行走时跳位。 */
function crewSeatExit(anchor,direction, actor = null) {
    // 1、使用同角色原图登记的站立鞋底，按 24/12 等距投影的逆变换求出椅脚位置。
    const [x,y] = crewSeatFootOffset(actor, direction);
    return [anchor.approach[0]+0.5-x/48-y/24,anchor.approach[1]+0.5+x/48-y/24];
}

/** 因为每个角色的腿长和鞋底位置不同，需要读取配套片段的脚点并明确镜像轴。 */
function crewSeatFootOffset(actor, direction) {
    // 1、旧的合成测试保留默认规格；正式角色从内置配套资源取得作者登记值。
    const point = actor?.chairFoot || [-24, 3];
    return [Math.abs(point[0]) * (direction === "ne" ? 1 : -1), point[1]];
}

/** 因为交互片段以椅脚定位而步行以鞋底定位，需要统一换算可见人物脚点以检查端点连续性。 */
function crewActorFootPosition(actor) {
    // 1、只在标准椅起坐时采用片段登记位移；其他姿态保持原世界脚点。
    const attached = crewAttachedSeat(actor);
    if (!crewStandardChair(attached, actor) || !["stand_up", "sit_down"].includes(actor.phase))
        return [...actor.position];
    const t = Math.max(0, Math.min(1, actor.poseProgress || 0));
    const offset = crewSeatFootOffset(actor, actor.direction);
    const x = offset[0] * t, y = offset[1] * t;
    return [actor.position[0] + x / 48 + y / 24,
        actor.position[1] - x / 48 + y / 24];
}

/** 因为椅子转向不能突然翻面，需要沿最短八方向序列逐步转过。 */
function crewTurnDirection(from,to,progress) {
    // 1、只影响展示朝向，不改变空间或任务权限。
    const a=CREW_DIRECTIONS.indexOf(from),b=CREW_DIRECTIONS.indexOf(to);
    const delta=((b-a+12)%8)-4;
    return CREW_DIRECTIONS[(Math.round(a+delta*progress)+8)%8];
}

/** 因为人物离座与入座绑定不同对象，需要统一取得当前实际接触的椅子。 */
function crewAttachedSeat(actor) {
    // 1、途中没有绑定椅子，起身和离座转向仍归原座位。
    if(actor.phase==="moving")return null;
    return ["seat_turn","stand_up"].includes(actor.phase)?actor.sourceSeat:actor.target;
}
