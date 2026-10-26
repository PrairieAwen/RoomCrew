/* 无需前端构建工具：验证素材协议与可丢弃动画状态机。 */
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const context = vm.createContext({});
vm.runInContext(
    fs.readFileSync("desktop/ui/studio/protocol.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/navigation.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/motion.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/leisure.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/collaboration.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/animation.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/skins.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/rig.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/controller.js", "utf8") +
        "\nglobalThis.testApi={crewState,crewProject,CrewMotion,CrewAnimator,crewSelectClip,crewPose,crewLeisureProfile,crewAtlasDirection,CrewStudio,CrewNavigator,CrewIdleDirector,CrewCollaborationDirector,crewIdleProfile};",
    context,
);
const {
    crewState,
    crewProject,
    CrewMotion,
    CrewAnimator,
    crewSelectClip,
    crewPose,
    crewLeisureProfile,
    crewAtlasDirection,
    CrewStudio,
    CrewNavigator,
    CrewIdleDirector,
    CrewCollaborationDirector,
    crewIdleProfile,
} = context.testApi;

/** 因为缺失素材或协议升级不能让画面执行任意输入，需要验证有限动作和版本回退。 */
function verifyProtocol() {
    // 1、未知动作回退 idle；未知协议版本与负序号拒绝。
    assert.equal(
        crewState({
            protocol_version: 1,
            activity: "executing",
            source_seq: 4,
            action_id: "https://evil",
        }).action_id,
        "idle",
    );
    assert.equal(
        crewState({ protocol_version: 99, activity: "idle", source_seq: 1 }),
        null,
    );
    assert.equal(
        crewState({ protocol_version: 1, activity: "idle", source_seq: -1 }),
        null,
    );
    assert.deepEqual(Array.from(crewProject([2, 1])), [24, 36]);
}

/** 因为人物不能坐着行走或重连后补播旧动画，需要验证代次、步长与恢复语义。 */
function verifyMotion() {
    // 1、换座先站立，行走完成后才使用目标坐姿。
    const motion = new CrewMotion();
    const first = {
        id: "desk",
        position: [1, 1],
        approach: [1, 2],
        posture: "seated",
    };
    const target = {
        id: "sofa",
        position: [1, 4.5],
        approach: [1, 5],
        posture: "seated",
    };
    motion.restore(
        { member_id: "boss", anchor_id: "desk", generation: 1 },
        [first, target],
        1,
    );
    const plan = {
        member_id: "boss",
        generation: 2,
        scene_revision: 1,
        plan_id: "one",
        mode: "presentation_only",
        route: [
            [1, 2],
            [1, 3],
            [1, 4],
            [1, 5],
        ],
        source: first,
        target,
    };
    assert(motion.accept(plan));
    assert.equal(motion.actors.get("boss").posture, "standing");
    motion.step(50);
    assert(
        motion.actors.get("boss").position[1] <= 2.21,
        "长帧应被限制而非瞬移",
    );
    for (let i = 0; i < 100; i++) motion.step(0.05);
    assert.equal(motion.actors.get("boss").posture, "seated");
    assert.equal(motion.accept(plan), false, "重复计划不能重播");
    // 2、快照先到时允许随后同代次计划只播放一次；重连直接落在稳定目标。
    const reconnected = new CrewMotion();
    reconnected.restore(
        { member_id: "boss", anchor_id: "sofa", generation: 2 },
        [first, target],
        1,
    );
    assert.equal(reconnected.actors.get("boss").route.length, 0);
    assert(reconnected.accept(plan));
    assert(!reconnected.accept(plan));
    reconnected.settle();
    assert.equal(reconnected.actors.get("boss").posture, "seated");
    assert(!reconnected.accept({ ...plan, generation: 1 }));
}

verifyProtocol();
verifyMotion();

/** 因为轨迹动作与表情必须正交，需要验证移动中保留人工提示且旁白不能覆盖真实工具。 */
function verifyTraceAnimation() {
    // 1、模型旁白的 action_id 不能覆盖事实细化后的书写动作。
    const animator = new CrewAnimator(),
        actor = {
            phase: "settled",
            posture: "seated",
            seatMix: 1,
            direction: "se",
        };
    const fact = {
        activity: "executing",
        action_id: "read",
        origin: "model",
        question_count: 0,
        warning_count: 0,
        animation: { gesture: "write", expression: "focused" },
    };
    assert.equal(animator.sample("a", fact, actor, 0.016).action, "write");
    const running = {
        ...actor,
        phase: "moving",
        posture: "standing",
        seatMix: 0,
        gait: "run",
    };
    const questioned = {
        ...fact,
        question_count: 1,
        animation: { gesture: "write", expression: "curious" },
    };
    const sample = animator.sample("a", questioned, running, 0.016);
    assert.equal(sample.action, "run");
    assert.equal(sample.expression, "curious");
    assert.equal(sample.posture, "standing");
    // 2、同一事实线索只入队一次，过期历史和取消任务不能继续播放。
    const cue = {
        member_id: "b",
        source_seq: 8,
        action: "read",
        expression: "focused",
        duration_ms: 320,
        created_at: new Date().toISOString(),
        visual_only: true,
    };
    animator.offer([cue, cue]);
    assert.equal(animator.queues.get("b").length, 1);
    animator.sample(
        "b",
        {
            activity: "question",
            question_count: 1,
            animation: { gesture: "ask", expression: "curious" },
        },
        actor,
        0.016,
    );
    assert.equal(animator.queues.get("b").length, 0);
    const walk = crewPose({ action: "walk", time: 0.2, seatMix: 0 }),
        run = crewPose({ action: "run", time: 0.2, seatMix: 0 });
    assert.notEqual(walk.lean, run.lean);
    assert.notEqual(walk.kneeR, run.kneeR);
    const aged = animator.sample(
        "old",
        {
            source_seq: 40,
            created_at: new Date(Date.now() - 10000).toISOString(),
            activity: "reporting",
            animation: { gesture: "report", expression: "smile" },
        },
        actor,
        0.016,
    );
    assert.equal(aged.action, "idle", "历史终态不应永久举着汇报文件");
}

/** 因为用户素材可能缺少变体，需要验证坐姿不使用站姿，表情与朝向能独立选择。 */
function verifyAtlasVariants() {
    // 1、表情精确变体优先，同姿态 idle 可回退，整个姿态缺失时使用内置骨架。
    const manifest = {
        clips: [
            {
                action: "idle",
                posture: "standing",
                direction: "s",
                expression: "neutral",
            },
            {
                action: "run",
                posture: "standing",
                direction: "se",
                expression: "neutral",
            },
            {
                action: "run",
                posture: "standing",
                direction: "se",
                expression: "curious",
            },
        ],
    };
    assert.equal(
        crewSelectClip(manifest, {
            action: "run",
            posture: "standing",
            direction: "se",
            expression: "curious",
        }).expression,
        "curious",
    );
    assert.equal(
        crewSelectClip(manifest, {
            action: "write",
            posture: "standing",
            direction: "n",
            expression: "focused",
        }).action,
        "idle",
    );
    assert.equal(
        crewSelectClip(manifest, {
            action: "run",
            posture: "seated",
            direction: "se",
            expression: "neutral",
        }),
        null,
    );
}

verifyTraceAnimation();
verifyAtlasVariants();

/** 因为空闲不是工具暂时没输出，需要验证人物偏好、全部上下文与即时打断的优先级。 */
function verifyLeisure() {
    // 1、人物独立选择动作，有限配置不允许基础设施、停用形象或任意外部动作。
    assert.equal(
        crewLeisureProfile({ role: "guardian", leisure_action: "phone" }),
        null,
    );
    assert.equal(
        crewLeisureProfile({ role: "employee", enabled: false }),
        null,
    );
    assert.equal(crewLeisureProfile({ leisure_action: "__proto__" }), null);
    assert.equal(crewLeisureProfile({ leisure_delay: NaN }), null);
    assert.equal(crewLeisureProfile({ leisure_action: "none" }), null);
    const animator = new CrewAnimator();
    const actor = {
        phase: "settled",
        posture: "seated",
        seatMix: 1,
        direction: "se",
    };
    const profile = { action: "phone", delay: 2 };
    const free = {
        source_seq: 1,
        activity: "idle",
        idle_eligible: true,
        active_contexts: 0,
        question_count: 0,
        warning_count: 0,
    };
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, profile, 0).leisure,
        false,
    );
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, profile, 1999).leisure,
        false,
    );
    const phone = animator.sample(
        "a",
        free,
        actor,
        0.016,
        false,
        profile,
        2000,
    );
    assert.equal(phone.action, "phone");
    assert.equal(phone.posture, "seated");
    assert.equal(phone.leisure, true);
    // 2、真实工作立即打断；其他上下文、人工、提醒、移动和数据不可用都不能被误判为空闲。
    const busy = {
        ...free,
        source_seq: 2,
        activity: "thinking",
        active_contexts: 1,
        idle_eligible: false,
        animation: { gesture: "think", expression: "focused" },
    };
    assert.equal(
        animator.sample("a", busy, actor, 0.016, false, profile, 2001).action,
        "think",
    );
    for (const blocked of [
        busy,
        { ...free, active_contexts: 1 },
        { ...free, question_count: 1 },
        { ...free, warning_count: 1 },
        { ...free, requires_input: true },
        { ...free, activity: "waiting" },
        { ...free, idle_eligible: false },
        { ...free, idle_eligible: undefined },
    ]) {
        assert.equal(
            animator.sample(
                "blocked",
                blocked,
                actor,
                0.016,
                false,
                { action: "water", delay: 0 },
                10000,
            ).leisure,
            false,
        );
    }
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, profile, 2002).leisure,
        false,
    );
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, profile, 4002).leisure,
        true,
    );
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, null, 4003).leisure,
        false,
        "断线需要立即停掉摸鱼",
    );
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, profile, 4004).leisure,
        false,
    );
    const moving = { ...actor, phase: "moving", gait: "run" };
    assert.equal(
        animator.sample("a", free, moving, 0.016, false, profile, 50000).action,
        "run",
    );
    assert.equal(
        animator.sample("a", free, actor, 0.016, true, profile, 50000).leisure,
        false,
    );
    // 3、各形象时钟独立，清理历史与更改配置重新等待；完成汇报先展示再进入空闲。
    assert.equal(
        animator.sample(
            "b",
            null,
            actor,
            0.016,
            false,
            { action: "game", delay: 0 },
            50001,
        ).action,
        "game",
    );
    assert.equal(
        animator.sample(
            "c",
            free,
            actor,
            0.016,
            false,
            { action: "water", delay: 0 },
            50001,
        ).action,
        "water",
    );
    animator.clear();
    assert.equal(
        animator.sample("a", free, actor, 0.016, false, profile, 50002).leisure,
        false,
    );
    const report = {
        ...free,
        source_seq: 7,
        activity: "reporting",
        created_at: new Date().toISOString(),
        animation: { gesture: "report", expression: "smile" },
    };
    assert.equal(
        animator.sample(
            "report",
            report,
            actor,
            0.016,
            false,
            { action: "game", delay: 0 },
            0,
        ).action,
        "report",
    );
    // 4、自绘生活片段可精确选择；缺少生活片段返回内置骨架，不能用闲置帧冒充手机动作。
    const clip = {
        action: "phone",
        posture: "seated",
        direction: "se",
        expression: "smile",
    };
    assert.equal(crewSelectClip({ clips: [clip] }, phone), clip);
    assert.equal(
        crewSelectClip({ clips: [{ ...clip, action: "idle" }] }, phone),
        null,
    );
    const poses = ["phone", "game", "water", "relax"].map(leisurePose);
    assert.equal(new Set(poses.map(JSON.stringify)).size, 4);
}

/** 因为生活动作应有不同骨架目标，需要复用正式姿态求值器检查道具接触姿势。 */
function leisurePose(action) {
    // 1、统一采样时刻，不能靠名称变化冒充关节变化。
    return crewPose({ action, time: 0.4, seatMix: 1 });
}

verifyLeisure();

/** 因为手绘角色的背面不能用正面遮脸模拟，需要验证镜像朝向选择了真实背面片段。 */
function verifyPortraitDirections() {
    // 1、镜像由素材明确声明，普通素材继续保留原朝向行为。
    assert.equal(crewAtlasDirection({ mirror_west: true }, "nw"), "ne");
    assert.equal(crewAtlasDirection({ mirror_west: false }, "nw"), "nw");
    const front = {
        action: "walk",
        posture: "standing",
        direction: "se",
        expression: "neutral",
    };
    const back = { ...front, direction: "ne" };
    const value = crewSelectClip(
        { mirror_west: true, clips: [front, back] },
        {
            action: "walk",
            posture: "standing",
            direction: "nw",
            expression: "neutral",
        },
    );
    assert.equal(value, back);
}
verifyPortraitDirections();

/** 因为隔离素材页只能请求关闭自身，需要验证其他来源与其他消息不能触发主窗口操作。 */
function verifyGalleryMessageBoundary() {
    // 1、只隔离窗口来源，不实例化界面、桌面桥或任务执行器。
    const frame = { contentWindow: {} };
    let closed = 0;
    /** 因为测试只验证固定 iframe，需要提供有限 DOM 查询替身。 */
    function galleryFrame(identifier) {
        // 1、其他元素不能被该消息处理器访问。
        assert.equal(identifier, "asset-library-frame");
        return frame;
    }
    /** 因为关闭不应包含其他业务效果，需要仅统计被允许的 UI 请求。 */
    function closeGallery() {
        // 1、不替代任何生产 Agent 或模型结果。
        closed++;
    }
    context.el = galleryFrame;
    const receiver = { closeAssetLibrary: closeGallery };
    CrewStudio.prototype.galleryMessage.call(receiver, {
        source: {},
        data: { type: "roomcrew.material.close" },
    });
    CrewStudio.prototype.galleryMessage.call(receiver, {
        source: frame.contentWindow,
        data: { type: "run.complete" },
    });
    assert.equal(closed, 0);
    CrewStudio.prototype.galleryMessage.call(receiver, {
        source: frame.contentWindow,
        data: { type: "roomcrew.material.close" },
    });
    assert.equal(closed, 1);
}
verifyGalleryMessageBoundary();

/** 因为轮换等待五至十分钟不能靠人工挂机验收，需要用注入时钟验证边界而不改变生产计时。 */
function verifyIdleRotationAndInterruption() {
    // 1、同一正式导演在 299999 毫秒前不能换活动，达到注入随机数决定的 300000 毫秒后才换。
    const nav = new CrewNavigator();
    nav.update({
        version: 1,
        revision: 1,
        width: 10,
        height: 10,
        blocked: [
            [4, 4],
            [4, 5],
        ],
    });
    const motion = new CrewMotion(),
        anchor = {
            id: "home",
            position: [2, 2],
            approach: [2, 2],
            posture: "standing",
        };
    motion.restore(
        { member_id: "a", anchor_id: "home", generation: 1 },
        [anchor],
        1,
    );
    const director = new CrewIdleDirector(motion, nav, zeroRandom);
    const views = new Map([
            [
                "a",
                {
                    member: {
                        id: "a",
                        role: "employee",
                        enabled: true,
                        leisure_actions: ["phone", "game"],
                        leisure_delay: 0,
                    },
                },
            ],
        ]),
        facts = new Map();
    director.tick(views, facts, true, 0);
    assert.equal(director.hints.get("a").activity, "phone");
    director.tick(views, facts, true, 299999);
    assert.equal(director.hints.get("a").activity, "phone");
    director.tick(views, facts, true, 300000);
    assert.equal(director.hints.get("a").activity, "game");
    assert.equal(director.states.get("a").nextAt, 600000);
    const busy = {
        idle_eligible: false,
        active_contexts: 1,
        question_count: 0,
        warning_count: 0,
        activity: "thinking",
    };
    facts.set("a", busy);
    director.tick(views, facts, true, 300001);
    assert.equal(director.hints.has("a"), false);
    facts.clear();
    director.engage("a", 300002);
    director.tick(views, facts, true, 300003);
    assert.equal(director.hints.has("a"), false);
    // 2、导航只能使用可走格，会议和散步返回后不更改持久化代次。
    const route = nav.route([2, 2], [6, 6]);
    assert(route.length > 0);
    for (const point of route) assert(nav.free(point));
    motion.visualMove(
        "a",
        route,
        { id: "walk", position: [6, 6], approach: [6, 6], posture: "standing" },
        "leisure",
    );
    for (let i = 0; i < 150; i++) motion.step(0.05);
    assert.equal(motion.actors.get("a").generation, 1);
    motion.returnVisual("a", nav);
    for (let i = 0; i < 150; i++) motion.step(0.05);
    assert.deepEqual(Array.from(motion.actors.get("a").position), [2, 2]);
    assert.equal(motion.actors.get("a").visualKind, undefined);
    assert.equal(crewIdleProfile({ role: "user" }), null);
    assert.equal(
        crewIdleProfile({
            role: "employee",
            leisure_actions: ["phone", "game", "wander", "chat", "water"],
        }),
        null,
    );
}

/** 因为计时验证需要精确落在最短轮换边界，需要注入合法的固定随机值。 */
function zeroRandom() {
    // 1、只用于测试，生产默认使用 Math.random。
    return 0;
}

/** 因为同任务会议和外援电话不能混淆，需要验证真实关系驱动的临时站位及退出。 */
function verifyMeetingAndExternalCall() {
    // 1、两个人物仅消费明确配置的会议关系；不调用桌面桥或生成任务。
    const nav = new CrewNavigator();
    nav.update({ version: 1, revision: 1, width: 10, height: 10, blocked: [] });
    const motion = new CrewMotion(),
        home = {
            id: "home",
            position: [1, 1],
            approach: [1, 1],
            posture: "standing",
        },
        home2 = { ...home, id: "home2", position: [2, 1], approach: [2, 1] };
    motion.restore(
        { member_id: "a", anchor_id: "home", generation: 1 },
        [home],
        1,
    );
    motion.restore(
        { member_id: "b", anchor_id: "home2", generation: 1 },
        [home2],
        1,
    );
    const views = new Map([
        ["a", { member: { role: "assistant", enabled: true } }],
        ["b", { member: { role: "employee", enabled: true } }],
    ]);
    const scene = {
        room: { objects: [{ id: "m", type: "meeting" }] },
        anchors: [
            {
                id: "seat1",
                object_id: "m",
                position: [6, 6],
                approach: [6, 6],
                posture: "seated",
            },
            {
                id: "seat2",
                object_id: "m",
                position: [7, 6],
                approach: [7, 6],
                posture: "seated",
            },
        ],
        placements: [],
    };
    const director = new CrewCollaborationDirector(motion, nav),
        groups = [{ kind: "meeting", group_id: "run-1", members: ["a", "b"] }];
    director.tick(groups, scene, views, new Map(), true, 0);
    assert.equal(director.assignments.size, 2);
    for (let i = 0; i < 100; i++) motion.step(0.05);
    director.tick(groups, scene, views, new Map(), true, 5000);
    assert.equal(director.hints.get("a").kind, "meeting");
    assert.equal(motion.actors.get("a").posture, "standing");
    director.tick([], scene, views, new Map(), true, 5001);
    assert.equal(director.hints.size, 0);
    assert.equal(motion.actors.get("a").visualKind, "return");
    const animator = new CrewAnimator();
    const call = animator.sample(
        "a",
        {
            activity: "delegating",
            external_calls: 1,
            animation: { gesture: "talk", expression: "focused" },
        },
        { ...motion.actors.get("a"), phase: "settled" },
        0.016,
        false,
        null,
        5002,
    );
    assert.equal(call.externalCall, true);
    assert.equal(call.leisure, false);
    assert.equal(call.action, "phone");
    assert.equal(views.size, 2, "外援不生成新人物");
}

verifyIdleRotationAndInterruption();
verifyMeetingAndExternalCall();

/** 因为假聊天不能继续拉住已经接单的同事，需要验证双人配对会被真实工作原子解除。 */
function verifyIdleChatPair() {
    // 1、两名同事用正式导航与导演自行配对，测试不生成聊天消息或 Agent 响应。
    const nav = new CrewNavigator();
    nav.update({ version: 1, revision: 1, width: 10, height: 10, blocked: [] });
    const motion = new CrewMotion();
    for (const [id, point] of [
        ["a", [2, 2]],
        ["b", [5, 2]],
    ]) {
        const anchor = {
            id,
            position: point,
            approach: point,
            posture: "standing",
        };
        motion.restore(
            { member_id: id, anchor_id: id, generation: 1 },
            [anchor],
            1,
        );
    }
    const members = new Map([
        [
            "a",
            {
                member: {
                    role: "employee",
                    enabled: true,
                    leisure_actions: ["chat"],
                    leisure_delay: 0,
                },
            },
        ],
        [
            "b",
            {
                member: {
                    role: "employee",
                    enabled: true,
                    leisure_actions: ["chat"],
                    leisure_delay: 0,
                },
            },
        ],
    ]);
    const director = new CrewIdleDirector(motion, nav, zeroRandom),
        facts = new Map();
    director.tick(members, facts, true, 0);
    assert.equal(director.states.get("a").partner, "b");
    assert.equal(director.states.get("b").partner, "a");
    const target = motion.actors.get("a").target.position,
        peer = motion.actors.get("b").position;
    assert(
        Math.abs(target[0] - peer[0]) + Math.abs(target[1] - peer[1]) >= 4,
        "闲聊人物保持社交间距",
    );
    facts.set("b", {
        idle_eligible: false,
        activity: "thinking",
        active_contexts: 1,
        question_count: 0,
        warning_count: 0,
    });
    director.tick(members, facts, true, 1);
    assert.equal(director.hints.has("b"), false);
    assert.equal(director.states.get("a")?.partner, null);
    assert.equal(
        motion.actors.get("a").visualKind,
        "return",
        "同事接单后停止旧闲聊路线",
    );
}
verifyIdleChatPair();
process.stdout.write("protocol + motion + animation + leisure: passed\n");
