/* 表现协议 v1：素材动作与执行事实隔离，可在无 DOM 环境验证。 */
"use strict";
const CREW_ACTION_LABELS = {
    idle: "待命",
    think: "思考",
    read: "阅读",
    type: "打字",
    write: "书写",
    work: "工作",
    talk: "交谈",
    ask: "举手询问",
    report: "汇报",
    alert: "提醒",
    listen: "倾听",
    walk: "走路",
    run: "小跑",
    sit_down: "落座",
    stand_up: "起身",
    sit: "坐着",
    phone: "玩手机",
    game: "打游戏",
    water: "浇花",
    relax: "自定义休闲",
};
const CREW_EXPRESSION_LABELS = {
    neutral: "中性",
    focused: "专注",
    curious: "疑问",
    concerned: "担忧",
    smile: "微笑",
};
const CREW_DIRECTION_LABELS = {
    e: "右",
    se: "右下",
    s: "下",
    sw: "左下",
    w: "左",
    nw: "左上",
    n: "上",
    ne: "右上",
};
const CREW_CLIPS = Object.freeze({
    idle: { fps: 24, frames: 24 },
    think: { fps: 6, frames: 4 },
    read: { fps: 6, frames: 4 },
    work: { fps: 10, frames: 6 },
    talk: { fps: 8, frames: 4 },
    ask: { fps: 5, frames: 4 },
    report: { fps: 6, frames: 4 },
    alert: { fps: 5, frames: 4 },
    listen: { fps: 4, frames: 4 },
    walk: { fps: 24, frames: 24 },
    run: { fps: 30, frames: 24 },
    type: { fps: 24, frames: 24 },
    write: { fps: 24, frames: 24 },
    sit_down: { fps: 30, frames: 12 },
    stand_up: { fps: 30, frames: 12 },
    sit: { fps: 24, frames: 24 },
    phone: { fps: 24, frames: 48 },
    game: { fps: 24, frames: 48 },
    water: { fps: 24, frames: 72 },
    relax: { fps: 24, frames: 72 },
});
const CREW_LEISURE_ACTIONS = new Set(["phone", "game", "water", "relax"]);
const CREW_IDLE_ACTIVITIES = new Set([
    "phone",
    "game",
    "wander",
    "chat",
    "water",
    "relax",
]);
const CREW_IDLE_LABELS = {
    phone: "玩手机",
    game: "打电脑游戏",
    wander: "办公室散步",
    chat: "同事闲聊",
    water: "浇花",
    relax: "自定义休闲",
};

/** 因为旧账号没有空闲偏好且形象可以共享 Agent，需要独立解析每个人物的有限生活动作。 */
function crewLeisureProfile(member) {
    // 1、停用人物和基础设施保持值守；外部数据不能新增动作名或任意等待值。
    if (member.role === "guardian" || member.enabled === false) return null;
    const action =
        member.leisure_action ??
        (member.role === "employee" ? "game" : "phone");
    const delay = member.leisure_delay ?? 5;
    if (
        !CREW_LEISURE_ACTIONS.has(action) ||
        !Number.isInteger(delay) ||
        delay < 0 ||
        delay > 120
    )
        return null;
    return { action, delay };
}

/** 因为空闲活动需要每五至十分钟随机轮换，需要解析最多四项的人物活动池并兼容旧配置。 */
function crewIdleProfile(member) {
    // 1、用户没有场景替身，基础设施和停用人物保持值守。
    if (["user", "guardian"].includes(member.role) || member.enabled === false)
        return null;
    const delay = member.leisure_delay ?? 5;
    let actions = member.leisure_actions;
    if (actions === undefined)
        actions =
            member.leisure_action === "none"
                ? []
                : ["phone", "game", "wander", "chat"];
    if (
        !Array.isArray(actions) ||
        actions.length > 4 ||
        new Set(actions).size !== actions.length ||
        actions.some(crewUnknownIdle) ||
        !Number.isInteger(delay) ||
        delay < 0 ||
        delay > 120
    )
        return null;
    return actions.length ? { actions: [...actions], delay } : null;
}

/** 因为活动池不能新增脚本名，需要用同一有限词表验证各项。 */
function crewUnknownIdle(value) {
    // 1、所有活动仅是本地表现语义。
    return !CREW_IDLE_ACTIVITIES.has(value);
}

/** 因为任务没有输出不等于空闲，需要在所有生活交互中复用同一个确定性判定。 */
function crewIdleEligible(fact) {
    // 1、新人物在完整健康快照中可空闲；已有事实必须显式确认全部上下文和瓶颈已清空。
    return (
        !fact ||
        (fact.idle_eligible === true &&
            fact.active_contexts === 0 &&
            fact.question_count === 0 &&
            fact.warning_count === 0 &&
            !fact.requires_input &&
            ["idle", "reporting", "stopped"].includes(fact.activity))
    );
}
const CREW_EXPRESSIONS = new Set([
    "neutral",
    "focused",
    "curious",
    "concerned",
    "smile",
]);
const CREW_DIRECTIONS = ["e", "se", "s", "sw", "w", "nw", "n", "ne"];
const CREW_ACTIVITIES = new Set([
    "idle",
    "thinking",
    "executing",
    "delegating",
    "question",
    "waiting",
    "reporting",
    "warning",
    "stopped",
    "receiving",
]);

/** 因为协议与素材可能跨版本升级，需要验证有限状态并为缺失动作提供 idle 回退。 */
function crewState(value) {
    // 1、模型不能通过协议提供任意 URL、帧号、脚本或权限指令。
    if (
        value.protocol_version !== 1 ||
        !CREW_ACTIVITIES.has(value.activity) ||
        !Number.isSafeInteger(value.source_seq) ||
        value.source_seq < 0
    )
        return null;
    return {
        ...value,
        action_id: Object.hasOwn(CREW_CLIPS, value.action_id)
            ? value.action_id
            : "idle",
    };
}

/** 因为投影使用世界格网而美术使用像素，需要统一采用同一套 2:1 等距投影。 */
function crewProject(position) {
    // 1、角色脚底、家具占地和地面选择都使用同一个公式。
    return [(position[0] - position[1]) * 24, (position[0] + position[1]) * 12];
}

/** 因为锚点检索需要可测试的具名谓词，需要按稳定 ID 比较而不按显示名称。 */
function crewAnchorMatches(anchor) {
    // 1、thisArg 只来自本地受验证的锚点标识。
    return anchor.id === String(this);
}
