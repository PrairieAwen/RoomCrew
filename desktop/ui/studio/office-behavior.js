/* 办公接触、朝向和内置手绘补帧；不读取或修改 Agent 执行。 */
"use strict";

/** 因为工作、休闲和面对用户有不同朝向，需要以座位用途与当前动作决定目标方向。 */
function crewOfficeFacing(actor, action, fact, layer) {
    // 1、工作与电脑游戏都面向显示器；会议沿实际座位朝向，不能全员面对镜头。
    if (layer?.kind === "performance" && layer.direction) return layer.direction;
    if (actor.target?.purpose === "workstation") {
        if (
            fact?.requires_input ||
            (fact?.activity === "reporting" &&
                fact?.bubble &&
                !fact.report_acknowledged)
        )
            return "se";
        if (
            ["phone", "relax", "talk", "report", "ask"].includes(action) &&
            layer?.kind !== "meeting"
        )
            return "se";
        return actor.target.direction || "ne";
    }
    // 2、沙发默认向用户，临时会议和散步仍使用各自的导航目标。
    if (fact?.requires_input) return "se";
    return actor.target?.direction || actor.direction || "se";
}

/** 因为工作语义不意味着附近存在电脑，需要把无显示器处的打字降级为思考、电脑游戏降级为手机。 */
function crewOfficeAction(actor, action) {
    // 1、实际执行结果不变；只有稳定在非工位时才限制不合物理条件的动作。
    if (actor.phase === "settled" && actor.target?.purpose !== "workstation") {
        if (["work", "type"].includes(action)) return "think";
        if (action === "game") return "phone";
    }
    return action;
}

/** 因为旧的显式帧可能把背向电脑工作又改回正面，需要先验证物理兼容性，原配置继续保留。 */
function crewOfficeBindingCompatible(binding, sample) {
    // 1、无电脑处不重新注入打字帧；人工和完成仍可使用用户自定义的正面表情。
    if (binding.action !== sample.action) return false;
    if (
        !binding.clip ||
        sample.surface !== "workstation" ||
        !["ne", "n", "nw"].includes(sample.direction)
    ) return true;
    const [, direction, posture] = binding.clip.split(".");
    return posture === sample.posture && direction === sample.direction;
}

class CrewWorkstationDirector {
    /** 因为用户可把人物放在沙发但电脑工作仍需要工位，需要独立维护可丢弃的桌面借座。 */
    constructor(motion, navigator) {
        // 1、只持有表现对象，不持有模型或后端执行接口。
        this.motion = motion;
        this.navigator = navigator;
        this.borrowed = new Set();
    }

    /** 因为跨空间不能保留另一会议室的借座，需要清空本地引用。 */
    clear() {
        // 1、实际位置和任务由各自空间恢复。
        this.borrowed.clear();
    }

    /** 因为工作动作不能在沙发或会议席凭空打字，需要仅在真实忙碌且无会议时借用空工位。 */
    tick(scene, views, facts, meetings, healthy = true) {
        // 1、占用同时检查持久化座位和在途目标，不把两名人物送到同一桌前。
        if (!healthy) return;
        const used = new Set();
        for (const actor of this.motion.actors.values()) used.add(actor.target?.id);
        for (const place of scene?.placements || []) used.add(place.anchor_id);
        for (const [id, view] of views) {
            const actor = this.motion.actors.get(id),
                fact = facts.get(id);
            if (!actor || !["assistant", "employee"].includes(view.member.role))
                continue;
            const busy =
                fact?.active_contexts > 0 &&
                !["reporting", "stopped", "warning"].includes(fact.activity);
            if (!busy && this.borrowed.has(id)) {
                this.motion.returnVisual(id, this.navigator);
                this.borrowed.delete(id);
            }
            if (
                !busy ||
                fact.requires_input ||
                meetings.has(id) ||
                actor.phase !== "settled" ||
                actor.target?.purpose === "workstation"
            ) continue;
            // 2、有真实工作也不能穿桌或抢座；无空工位时由播放器使用非电脑的思考动作。
            for (const anchor of scene?.anchors || []) {
                if (anchor.purpose !== "workstation" || used.has(anchor.id))
                    continue;
                const route = this.navigator.route(actor.groundCell, anchor.approach);
                if (!route.length) continue;
                this.motion.visualMove(id, route, anchor, "work");
                used.add(anchor.id);
                this.borrowed.add(id);
                break;
            }
        }
    }
}

/** 因为坐着不能瞬间前后翻面，需要在相邻八向之间用独立、有界的转身时钟过渡。 */
function crewOfficeTurn(player, actor, desired, dt, reduced) {
    // 1、走路和起坐由运动层负责方向；稳定坐姿转向时先停止手部工作，再逐步转身。
    const controlled = actor.phase !== "settled" && !actor.interactionHold;
    if (player.heading == null || controlled || reduced) {
        player.heading = CREW_DIRECTIONS.indexOf(
            controlled ? actor.direction || desired : desired,
        );
        return { direction: CREW_DIRECTIONS[player.heading], turning: false };
    }
    const target = CREW_DIRECTIONS.indexOf(desired);
    const delta = ((target - player.heading + 12) % 8) - 4;
    const step = Math.min(Math.abs(delta), Math.max(0, dt) / 0.12);
    player.heading = (player.heading + Math.sign(delta) * step + 8) % 8;
    return {
        direction: CREW_DIRECTIONS[Math.round(player.heading) % 8],
        turning: Math.abs(delta) > step + 0.001,
    };
}

