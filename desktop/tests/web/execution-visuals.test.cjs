/* 执行事实优先、短工具动作与转身时长的回归。 */
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const context = vm.createContext({});
for (const file of ["protocol", "motion", "office-behavior", "animation"])
    vm.runInContext(fs.readFileSync(`desktop/ui/studio/${file}.js`, "utf8"), context);
vm.runInContext("globalThis.exportsForTest = {CrewAnimator};", context);
const { CrewAnimator } = context.exportsForTest;

/** 因为工具可能在一次轮询内结束，需要验证转向显示器之后仍有实际打字动作。 */
function verifyTypingAfterTurn() {
    // 1、先恢复面向用户的角色，再提交已经结束的短工具线索。
    const animator = new CrewAnimator();
    const actor = { phase: "settled", posture: "seated", direction: "se", target: {purpose: "workstation", direction: "nw"} };
    const now = Date.now();
    const fact = { source_seq: 1, created_at: new Date(now).toISOString(), activity: "thinking", active_contexts: 1, question_count: 0, warning_count: 0, animation: {gesture: "think", expression: "focused"} };
    animator.players.set("member", {time: 0, clock: 0, action: "idle", cue: null, heading: 1});
    animator.offer([{ member_id: "member", run_id: "run", source_seq: 1, created_at: new Date(now).toISOString(), action: "type", expression: "focused", duration_ms: 320, visual_only: true }], now);
    let typing = 0, turning = 0;
    for (let i = 0; i < 35; i++) {
        const sample = animator.sample("member", fact, actor, 0.04, false, null, now);
        if (sample.turning) turning++;
        if (sample.action === "type") {
            assert.equal(sample.direction, "nw");
            typing++;
        }
    }
    assert(turning > 0 && typing >= 5, "短线索不能全部消耗在转身上");
}

/** 因为上一轮完成动画可能迟到，需要保证当前执行时不会回放汇报姿势。 */
function verifyNoStaleReport() {
    // 1、即使完成线索还在有效期内，新任务仍保持实际工具动作。
    const animator = new CrewAnimator(), now = Date.now();
    const actor = { phase: "settled", posture: "seated", direction: "nw", target: {purpose: "workstation", direction: "nw"} };
    const fact = {source_seq: 5, activity: "executing", active_contexts: 1, question_count: 0, warning_count: 0, animation: {gesture: "type", expression: "focused"}};
    animator.offer([{member_id: "member", run_id: "old", source_seq: 4, created_at: new Date(now).toISOString(), action: "report", expression: "smile", duration_ms: 800, visual_only: true}], now);
    assert.equal(animator.sample("member", fact, actor, 0.04, false, null, now).action, "type");
    assert.equal(animator.queues.get("member").length, 0);
}

verifyTypingAfterTurn();
verifyNoStaleReport();
console.log("Execution visual regression passed");
