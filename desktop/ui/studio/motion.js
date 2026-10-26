/* 空间插值状态机：不决定任务状态，只消费已验证的格网路线。 */
"use strict";

class CrewMotion {
    /** 因为人物可以复用 Agent 而位置必须独立，需要按 member ID 维护显示状态。 */
    constructor() {
        // 1、任何移动状态均可从持久化目标恢复，不回调执行器。
        this.actors = new Map();
    }

    /** 因为重连不应重播历史走动，需要直接恢复到稳定目标与合法姿态。 */
    restore(placement, anchors, revision) {
        // 1、在途同代次保持原插值；布局变更或更新代次才重新定位。
        const old = this.actors.get(placement.member_id);
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
            revision,
            position: [...target.position],
            groundCell: [...target.approach],
            posture: target.posture,
            target,
            route: [],
            elapsed: 0,
            phase: "settled",
            progress: 1,
            direction: "se",
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
        const seated = snapshotFirst
            ? plan.source?.posture === "seated"
            : old?.posture === "seated" || old?.phase === "sit_down";
        const position = snapshotFirst
            ? plan.source.position
            : old?.position || plan.source?.position || plan.route[0];
        // 2、起身和行走分开；站着改路线时接回地面格，不传送到上次逻辑目标。
        this.actors.set(plan.member_id, {
            generation: plan.generation,
            revision: plan.scene_revision,
            planId: plan.plan_id,
            position: [...position],
            groundCell: [...plan.route[0]],
            posture: "standing",
            target: plan.target,
            route: plan.route.map(crewCopyPoint),
            elapsed: 0,
            direction: old?.direction || "se",
            gait: plan.gait === "run" ? "run" : "walk",
            phase: seated ? "stand_up" : "moving",
            progress: 0,
            from: [...position],
            approach: [...plan.route[0]],
            seatMix: seated ? 1 : 0,
        });
        return true;
    }

    /** 因为长帧不能穿过家具或跳过起坐，需要限制时间步并只推进当前动作阶段。 */
    step(seconds) {
        // 1、动画时钟不驱动 Agent；暂停页面后允许直接恢复稳定显示目标。
        const dt = Math.min(0.05, Math.max(0, seconds));
        for (const actor of this.actors.values()) {
            actor.elapsed += dt;
            if (actor.phase === "stand_up") {
                actor.progress = Math.min(1, actor.progress + dt / 0.32);
                actor.position = crewLerpPoint(
                    actor.from,
                    actor.approach,
                    crewEase(actor.progress),
                );
                actor.seatMix = 1 - crewEase(actor.progress);
                if (actor.progress === 1) actor.phase = "moving";
                continue;
            }
            if (actor.phase === "sit_down") {
                actor.progress = Math.min(1, actor.progress + dt / 0.38);
                actor.position = crewLerpPoint(
                    actor.from,
                    actor.target.position,
                    crewEase(actor.progress),
                );
                actor.seatMix = crewEase(actor.progress);
                if (actor.progress === 1) {
                    actor.phase = "settled";
                    actor.posture = "seated";
                    if (actor.visualKind === "return") {
                        delete actor.visualHome;
                        delete actor.visualKind;
                    }
                }
                continue;
            }
            if (actor.phase !== "moving") continue;
            // 2、速度按世界格计算；方向按投影后的真实移动向量决定，不直接旋转平面人物。
            const next = actor.route[0];
            if (!next) {
                this.arrive(actor);
                continue;
            }
            const dx = next[0] - actor.position[0],
                dy = next[1] - actor.position[1],
                distance = Math.hypot(dx, dy);
            const speed = actor.gait === "run" ? 5.4 : 2.8;
            if (distance > 0.001) actor.direction = crewDirection([dx, dy]);
            if (distance <= dt * speed) {
                actor.position = [...next];
                actor.groundCell = [...next];
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
        if (actor.target.posture === "seated") {
            actor.direction = actor.target.direction || "se";
            actor.phase = "sit_down";
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
            !["leisure", "meeting", "return"].includes(kind)
        )
            return false;
        const seated = actor.posture === "seated" || actor.phase === "sit_down";
        actor.visualHome ||= actor.target;
        actor.visualKind = kind;
        actor.from = [...actor.position];
        actor.approach = [...route[0]];
        actor.route = route.map(crewCopyPoint);
        actor.target = target;
        actor.posture = "standing";
        actor.phase = seated ? "stand_up" : "moving";
        actor.progress = 0;
        actor.seatMix = seated ? 1 : 0;
        actor.gait = kind === "meeting" ? "run" : "walk";
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
        delete actor.visualHome;
        delete actor.visualKind;
        actor.route = [];
        actor.position = [...actor.target.position];
        actor.groundCell = [...actor.target.approach];
        actor.posture = actor.target.posture;
        actor.phase = "settled";
        actor.progress = 1;
        actor.seatMix = actor.posture === "seated" ? 1 : 0;
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
