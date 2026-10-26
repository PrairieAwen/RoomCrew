/* 无模型、无桥接的空闲生活导演；活动轮换固定 300—600 秒。 */
"use strict";
const CREW_IDLE_MIN_MS = 300000;
const CREW_IDLE_MAX_MS = 600000;

class CrewIdleDirector {
    /** 因为随机活动需要可复现验证，需要注入随机源并按人物保存独立周期。 */
    constructor(motion, navigator, random = Math.random) {
        // 1、此对象不持有桌面桥，也不发送虚构对话。
        this.motion = motion;
        this.navigator = navigator;
        this.random = random;
        this.states = new Map();
        this.blocked = new Map();
        this.hints = new Map();
    }

    /** 因为真实点击应立即打断摸鱼，需要让人物待命一段时间以便用户安排工作。 */
    engage(identifier, now) {
        // 1、点击本身不伪造运行事件；五分钟内不自动恢复摸鱼。
        this.blocked.set(identifier, now + CREW_IDLE_MIN_MS);
        this.stop(identifier);
    }

    /** 因为聊天会牵涉两个人物，需要成对释放生活提示并恢复原有座位。 */
    stop(identifier) {
        // 1、释放的只有画面关系；不会调用模型或修改任何工作状态。
        const state = this.states.get(identifier);
        if (state?.partner) {
            const peer = this.states.get(state.partner);
            if (peer?.partner === identifier) {
                peer.partner = null;
                peer.activity = null;
                peer.since = null;
                if (
                    this.motion.actors.get(state.partner)?.visualKind ===
                    "leisure"
                )
                    this.motion.returnVisual(state.partner, this.navigator);
            }
            this.hints.delete(state.partner);
        }
        this.states.delete(identifier);
        this.hints.delete(identifier);
        if (this.motion.actors.get(identifier)?.visualKind === "leisure")
            this.motion.returnVisual(identifier, this.navigator);
    }

    /** 因为轮询可能降级，需要在隐藏或断线时丢弃全部生活表演而不补播。 */
    clear() {
        // 1、保留人工接管冷却，不积压旧闲聊或散步。
        for (const id of [...this.states.keys()]) this.stop(id);
        this.hints.clear();
    }

    /** 因为同一任务可跨人物执行，需要结合完整事实、人工冷却与空间占用选择当前空闲活动。 */
    tick(views, facts, healthy, now, meetingMembers = new Set()) {
        // 1、先统一判断可空闲人物，不能让一个仍有任务的同事被拉入假聊天。
        this.hints.clear();
        const available = new Map();
        for (const [id, view] of views) {
            const profile = crewIdleProfile(view.member),
                actor = this.motion.actors.get(id),
                fact = facts.get(id);
            const reporting =
                fact?.activity === "reporting" &&
                Date.now() - Date.parse(fact.created_at) < 5000;
            const allowed =
                healthy &&
                profile &&
                actor &&
                crewIdleEligible(fact) &&
                !reporting &&
                !meetingMembers.has(id) &&
                (this.blocked.get(id) || 0) <= now &&
                (!actor.visualKind ||
                    actor.visualKind === "leisure" ||
                    (actor.visualKind === "return" && this.states.has(id))) &&
                (actor.phase === "settled" ||
                    actor.visualKind === "leisure" ||
                    (actor.visualKind === "return" && this.states.has(id)));
            if (allowed) available.set(id, { profile, actor });
            else this.stop(id);
        }
        // 2、周期按单调时钟计算；真实任务、点击或配置变化才提前结束，不按帧数切活动。
        for (const [id, value] of available) {
            const signature = JSON.stringify(value.profile);
            let state = this.states.get(id);
            if (!state || state.signature !== signature) {
                this.stop(id);
                state = {
                    signature,
                    since: now,
                    activity: null,
                    nextAt: 0,
                    partner: null,
                    legAt: now,
                };
                this.states.set(id, state);
            }
            if (now - state.since < value.profile.delay * 1000) continue;
            if (state.partner && !available.has(state.partner)) {
                state.partner = null;
                state.activity = null;
            }
            if (!state.activity || now >= state.nextAt)
                this.choose(id, state, value.profile, available, now);
            if (state.activity === "wander")
                this.wander(id, state, value.actor, now);
            if (state.activity === "chat")
                this.chat(id, state, value.actor, available, now);
            if (state.partner && value.actor.phase === "settled") {
                const peer = this.motion.actors.get(state.partner);
                if (peer)
                    value.actor.direction = crewDirection([
                        peer.position[0] - value.actor.position[0],
                        peer.position[1] - value.actor.position[1],
                    ]);
            }
            if (state.activity) {
                const moving =
                    value.actor.visualKind === "leisure" &&
                    value.actor.phase !== "settled";
                this.hints.set(id, {
                    kind: "idle",
                    activity: state.activity,
                    action: moving
                        ? "walk"
                        : state.activity === "wander"
                          ? "idle"
                          : state.activity === "chat"
                            ? "talk"
                            : state.activity,
                    caption: `摸鱼 · ${CREW_IDLE_LABELS[state.activity]}${state.activity === "chat" ? "（场景表演）" : ""}`,
                    nextAt: state.nextAt,
                    partner: state.partner,
                });
            }
        }
    }

    /** 因为连续重复同一项会显得呆板，需要在可用活动中均匀随机且尽量避开上一项。 */
    choose(id, state, profile, available, now) {
        // 1、无人可聊时先排除闲聊，避免虚构一个不存在的同事。
        let pool = profile.actions.filter(crewIdleChoiceAllowed, {
            id,
            available,
            states: this.states,
        });
        const alternatives = pool.filter(crewDifferentIdle, state.activity);
        if (alternatives.length) pool = alternatives;
        if (!pool.length) return;
        const oldPartner = state.partner;
        if (oldPartner) {
            const peer = this.states.get(oldPartner);
            if (peer?.partner === id) {
                peer.partner = null;
                peer.activity = null;
                peer.since = now;
            }
        }
        state.partner = null;
        state.activity =
            pool[
                Math.min(
                    pool.length - 1,
                    Math.floor(this.random() * pool.length),
                )
            ];
        state.nextAt =
            now +
            CREW_IDLE_MIN_MS +
            this.random() * (CREW_IDLE_MAX_MS - CREW_IDLE_MIN_MS);
        state.legAt = now;
        if (
            state.activity !== "wander" &&
            this.motion.actors.get(id)?.visualKind === "leisure"
        )
            this.motion.returnVisual(id, this.navigator);
    }

    /** 因为散步需要实际移动，需要在空地分段避障并保持同一活动直到轮换时间。 */
    wander(id, state, actor, now) {
        // 1、每次只规划一小段，不能在帧回调中反复搜索或穿过家具。
        if (actor.phase !== "settled" || now < state.legAt) return;
        const occupied = new Set();
        for (const [other, value] of this.motion.actors)
            if (other !== id) occupied.add(value.groundCell.join(","));
        const candidates = this.navigator.nearby(actor.groundCell, occupied);
        if (!candidates.length) return;
        const point =
            candidates[
                Math.min(
                    candidates.length - 1,
                    Math.floor(this.random() * candidates.length),
                )
            ];
        const route = this.navigator.route(actor.groundCell, point);
        if (route.length)
            this.motion.visualMove(
                id,
                route,
                {
                    id: "ambient:" + id,
                    position: point,
                    approach: point,
                    posture: "standing",
                },
                "leisure",
            );
        state.legAt = now + 6000 + this.random() * 4000;
    }

    /** 因为假聊天需要两名真正空闲的同事，需要就近配对并只产生本地谈话动作。 */
    chat(id, state, actor, available, now) {
        // 1、同事被派工或点击后立即解除配对；不创建消息、Run 或模型请求。
        if (state.partner) return;
        if (now < (state.chatRetryAt || 0)) return;
        state.chatRetryAt = now + 2000;
        for (const [peer, value] of available) {
            const peerState = this.states.get(peer);
            if (
                peer === id ||
                !value.profile.actions.includes("chat") ||
                value.actor.phase !== "settled" ||
                value.actor.visualKind ||
                peerState?.partner
            )
                continue;
            const occupied = new Set();
            for (const [other, current] of this.motion.actors)
                if (other !== id) occupied.add(current.groundCell.join(","));
            const center = value.actor.groundCell;
            const positions = this.navigator
                .nearby(center, occupied)
                .filter(crewSocialDistance, center);
            positions.sort(crewChatPointDistance.bind(null, actor.groundCell));
            for (const point of positions.slice(0, 8)) {
                if (occupied.has(point.join(","))) continue;
                const route = this.navigator.route(actor.groundCell, point);
                if (!route.length) continue;
                const paired = peerState || {
                    signature: JSON.stringify(value.profile),
                    since: now - value.profile.delay * 1000,
                    activity: "chat",
                    nextAt: state.nextAt,
                    legAt: now,
                };
                paired.activity = "chat";
                paired.partner = id;
                paired.nextAt = state.nextAt;
                this.states.set(peer, paired);
                state.partner = peer;
                this.motion.visualMove(
                    id,
                    route,
                    {
                        id: "chat:" + peer,
                        position: point,
                        approach: point,
                        posture: "standing",
                    },
                    "leisure",
                );
                return;
            }
        }
        // 2、临时无可达同事则保持当前等待，不随机切换其他活动或制造假工作。
    }
}

/** 因为闲聊不能强拉忙碌或未启用闲聊的同事，需要在选活动时先检查可配对对象。 */
function crewIdleChoiceAllowed(action) {
    // 1、这里只读取有限配置和本地状态。
    if (action !== "chat") return true;
    for (const [id, value] of this.available)
        if (
            id !== this.id &&
            value.profile.actions.includes("chat") &&
            !this.states.get(id)?.partner &&
            value.actor.phase === "settled"
        )
            return true;
    return false;
}
/** 因为轮换应尽量避免原动作，需要按有限字符串比较上一项。 */
function crewDifferentIdle(action) {
    // 1、没有其他选项时允许保持原项。
    return action !== String(this);
}

/** 因为手绘人物比单格更宽，需要给闲聊保留四至五格的社交间距。 */
function crewSocialDistance(point) {
    // 1、限制可达候选，不用修改碰撞地图来实现装饰间隔。
    const distance =
        Math.abs(point[0] - this[0]) + Math.abs(point[1] - this[1]);
    return distance >= 4 && distance <= 5;
}

/** 因为同事应走向最近的可达交谈点，需要对社交候选做稳定距离排序。 */
function crewChatPointDistance(origin, a, b) {
    // 1、距离相等时使用原候选顺序，防止逐帧抖动。
    return (
        Math.abs(a[0] - origin[0]) +
        Math.abs(a[1] - origin[1]) -
        Math.abs(b[0] - origin[0]) -
        Math.abs(b[1] - origin[1])
    );
}
