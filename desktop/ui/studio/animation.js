/* 事实状态、可丢弃短线索与正交动作的仲裁。 */
"use strict";

class CrewAnimator {
    /** 因为多人工作和表情不能共享时钟，需要独立保存每个人物的动作进度。 */
    constructor() {
        // 1、队列有界，历史线索和模型文字均不能成为任务状态。
        this.players = new Map();
        this.queues = new Map();
        this.seen = new Map();
    }

    /** 因为快速工具事件可能在轮询前结束，需要短暂展示新近真实事件而跳过过期历史。 */
    offer(cues, now = Date.now()) {
        // 1、有限动作词表与时间窗控制输入；断线后的旧动作不补播。
        for (const cue of cues || []) {
            const age = now - Date.parse(cue.created_at),
                last = this.seen.get(cue.member_id) || 0;
            if (
                !cue.visual_only ||
                !Object.hasOwn(CREW_CLIPS, cue.action) ||
                !Number.isSafeInteger(cue.source_seq) ||
                !CREW_EXPRESSIONS.has(cue.expression) ||
                !Number.isFinite(age) ||
                age > 4000 ||
                age < -2000 ||
                cue.source_seq <= last
            )
                continue;
            this.seen.set(cue.member_id, cue.source_seq);
            const queue = this.queues.get(cue.member_id) || [];
            const value = {
                ...cue,
                duration: Math.max(0.2, Math.min(1, cue.duration_ms / 1000)),
                expires: now + 2200,
            };
            if (queue.at(-1)?.action === cue.action)
                queue[queue.length - 1] = value;
            else queue.push(value);
            this.queues.set(cue.member_id, queue.slice(-4));
        }
    }

    /** 因为移动、坐姿、工作和表情可以同时存在，需要按优先级生成单帧的合法表现快照。 */
    sample(
        member,
        fact,
        actor,
        dt,
        reduced = false,
        leisure = null,
        now = Date.now(),
        layer = null,
    ) {
        // 1、规则事实优先；人工和异常提示即时响应，不被历史工具动作或模型旁白延迟。
        let player = this.players.get(member);
        if (!player) {
            player = { time: 0, clock: 0, action: "idle", cue: null };
            this.players.set(member, player);
        }
        player.clock += dt;
        const hint = fact?.animation;
        let action = hint?.gesture || fact?.action_id || "idle";
        let expression = hint?.expression || "neutral";
        if (!Object.hasOwn(CREW_CLIPS, action)) action = "idle";
        if (!CREW_EXPRESSIONS.has(expression)) expression = "neutral";
        const urgent =
            fact?.question_count > 0 ||
            fact?.warning_count > 0 ||
            ["question", "warning"].includes(fact?.activity);
        const moving = actor.phase === "moving" && !actor.interactionHold,
            transition = ["stand_up", "sit_down", "turn_to_seat", "seat_turn", "seat_turn_in"].includes(
                actor.phase,
            );
        if (player.sourceSeq !== fact?.source_seq) {
            const age = (Date.now() - Date.parse(fact?.created_at)) / 1000;
            player.factAge = Number.isFinite(age) ? Math.max(0, age) : 0;
            player.sourceSeq = fact?.source_seq;
        } else player.factAge = (player.factAge || 0) + dt;
        // 2、短线索只修饰画面；移动时不堆积历史回放，问题和错误不会被其掩盖。
        let queue = this.queues.get(member) || [];
        queue = queue.filter(crewCueFresh, Date.now());
        this.queues.set(member, queue);
        if (urgent || reduced || fact?.activity === "stopped") {
            player.cue = null;
            queue.length = 0;
        }
        if (player.cue) {
            player.cue.left -= dt;
            if (player.cue.left <= 0) player.cue = null;
        }
        if (!urgent && !moving && !transition && !player.cue && queue.length) {
            const cue = queue.shift();
            player.cue = { ...cue, left: cue.duration };
        }
        if (player.cue && !urgent) {
            action = player.cue.action;
            expression = player.cue.expression;
        }
        if (
            !player.cue &&
            !queue.length &&
            player.factAge > 3 &&
            ["reporting", "warning"].includes(fact?.activity)
        ) {
            action = "idle";
            if (fact.activity === "reporting" && player.factAge > 5)
                expression = "neutral";
        }
        if (moving) action = actor.gait;
        if (transition)
            action = ["turn_to_seat","seat_turn","seat_turn_in"].includes(actor.phase) ? "idle" : actor.phase;
        if (urgent)
            expression =
                fact?.question_count > 0 || fact?.activity === "question"
                    ? "curious"
                    : fact?.warning_count > 0 || fact?.activity === "warning"
                      ? "concerned"
                      : "neutral";
        // 3、空闲需没有任何上下文、待答复或提醒；断线、移动、短线索和终态汇报都会重置等待。
        const eligible = Boolean(
            leisure &&
                CREW_LEISURE_ACTIONS.has(leisure.action) &&
                !urgent &&
                !moving &&
                !transition &&
                !player.cue &&
                !queue.length &&
                actor.phase === "settled" &&
                !reduced &&
                (!fact ||
                    (fact.idle_eligible === true &&
                        fact.active_contexts === 0 &&
                        fact.question_count === 0 &&
                        fact.warning_count === 0 &&
                        !fact.requires_input &&
                        ["idle", "reporting", "stopped"].includes(
                            fact.activity,
                        ))) &&
                (!fact || fact.activity !== "reporting" || player.factAge > 5),
        );
        const choice = leisure ? `${leisure.action}:${leisure.delay}` : "";
        if (player.leisureChoice !== choice) player.idleSince = null;
        player.leisureChoice = choice;
        if (!eligible) player.idleSince = null;
        else if (player.idleSince == null) player.idleSince = now;
        let relaxing =
            eligible && now - player.idleSince >= leisure.delay * 1000;
        if (relaxing) {
            action = leisure.action;
            expression = "smile";
        }
        // 4、会议和生活均只覆盖表现；真实人工/错误优先，外援内部工作不生成新人物动作。
        let caption = "",
            externalCall = false;
        const canDecorate = !urgent && !reduced && !actor.interactionHold;
        if (canDecorate && layer) {
            if (!moving && !transition) action = layer.action;
            expression = layer.kind === "idle" ? "smile" : "focused";
            relaxing = layer.kind === "idle";
            caption = layer.caption;
        }
        if (canDecorate && fact?.external_calls > 0) {
            externalCall = true;
            caption =
                layer?.kind === "meeting"
                    ? "协作讨论 · 同时联系已配置协作者"
                    : "联系已配置协作者 · 仅轨迹";
            if (!moving && !transition && layer?.kind !== "meeting")
                action = "phone";
            expression = "focused";
            relaxing = false;
        }
        // 5、工作面向显示器，暂停手部动作后再转向用户；移动与起坐沿运动层朝向。
        const desired =
            typeof crewOfficeFacing === "function"
                ? crewOfficeFacing(actor, action, fact, layer)
                : actor.direction || "se";
        const facing =
            typeof crewOfficeTurn === "function"
                ? crewOfficeTurn(player, actor, desired, dt, reduced)
                : { direction: desired, turning: false };
        if (facing.turning) action = "idle";
        // 6、没有显示器的座位不播放打字或电脑游戏；无空工位仍可思考，不伪造工具失败。
        if (typeof crewOfficeAction === "function") {
            const previousAction = action;
            action = crewOfficeAction(actor, action);
            if (previousAction === "game" && action === "phone")
                caption = "摸鱼 · 玩手机（此处没有电脑）";
        }
        // 7、切动作重置片段时钟，内置骨架用连续混合，自定义图集按声明帧率取帧。
        if (player.action !== action) {
            player.action = action;
            player.time = 0;
        } else player.time += dt;
        const spec = CREW_CLIPS[action] || CREW_CLIPS.idle;
        return {
            action,
            expression,
            time: player.time,
            clock: player.clock,
            frame: reduced
                ? 0
                : Math.floor(player.time * spec.fps) % spec.frames,
            locomotion: moving ? actor.gait : "idle",
            posture: ["seat_turn","seat_turn_in"].includes(actor.phase) ? "seated" : transition && actor.phase !== "turn_to_seat"
                ? (actor.seatMix >= 0.5 ? "seated" : "standing") : actor.posture,
            phase: actor.phase,
            transition_progress: actor.progress,
            pose_progress: actor.poseProgress,
            seatMix: actor.seatMix ?? (actor.posture === "seated" ? 1 : 0),
            direction: facing.direction,
            turning: facing.turning,
            surface: crewAttachedSeat(actor)?.purpose,
            seat_height: crewAttachedSeat(actor)?.contact?.seat_height,
            cue: Boolean(player.cue),
            reduced,
            leisure: relaxing,
            caption,
            externalCall,
            meeting: layer?.kind === "meeting",
            idleActivity: relaxing
                ? layer?.activity === "game" && action === "phone"
                    ? "phone"
                    : layer?.activity || action
                : null,
        };
    }

    /** 因为隐藏、重连或离开场景不应积压旧表现，需要丢弃短线索但保留真实事实。 */
    clear() {
        // 1、该方法不触碰后台 Run 或待答复记录。
        this.queues.clear();
        for (const player of this.players.values()) {
            player.cue = null;
            player.idleSince = null;
        }
    }
}

/** 因为队列不能保留过期动作，需要用具名谓词限制线索寿命。 */
function crewCueFresh(cue) {
    // 1、过期项静默丢弃，任务依然按真实状态继续显示。
    return cue.expires > Number(this);
}
