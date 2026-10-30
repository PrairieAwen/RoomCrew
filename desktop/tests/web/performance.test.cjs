/* 持久收件箱之外的纯表现状态机回归。 */
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const context = vm.createContext({});
for (const name of ["protocol", "navigation", "motion", "performance"])
    vm.runInContext(fs.readFileSync(`desktop/ui/studio/${name}.js`, "utf8"), context);
vm.runInContext("globalThis.fixture={CrewMotion,CrewNavigator,CrewActionDirector};", context);
const {CrewMotion, CrewNavigator, CrewActionDirector} = context.fixture;

/** 因为递文件需经过真实导航，需要建立三个独立人物和含档案库的合成会议室。 */
function fixture() {
    // 1、没有桌面桥、模型或执行器，运动仍使用生产插值器与导航器。
    const motion = new CrewMotion(), nav = new CrewNavigator(), views = new Map();
    nav.update({version:1,revision:1,width:14,height:14,blocked:[[9,2],[10,2]]});
    for (const [id, point] of [["lead",[2,2]],["a",[6,3]],["b",[6,8]]]) {
        const anchor={id,approach:point,position:point.map(center),posture:"standing",direction:"se"};
        motion.restore({member_id:id,anchor_id:id,generation:1},[anchor],1);
        views.set(id,{member:{id,name:id,role:"employee"}});
    }
    return {motion,views,director:new CrewActionDirector(motion,nav),scene:{room:{objects:[{id:"archive",type:"archive",x:9,y:2,footprint:[2,1]}]},placements:[]}};
}
/** 因为地面索引需要转世界脚点，需要使用与生产相同的格心。 */
function center(value) {
    // 1、不修改输入数组。
    return value+0.5;
}
/** 因为动作队列必须用真实事件身份去重，需要构造不同来源序号的明确任务目标。 */
function action(seq, kind, target = null) {
    // 1、时间可很旧，不能以四秒 TTL 丢弃已接收事件。
    return {id:String(seq),source_seq:seq,kind,member_id:"lead",target_member_id:target,run_id:"finished-run",visual_only:true,created_at:"2020-01-01T00:00:00Z"};
}

/** 因为 A、B 可以同一时刻受理，需要验证主角先后递文件且不把两者合并成开会。 */
function verifySequentialHandoffs() {
    // 1、后端已经结束也能播放；重复快照不重复入队。
    const f=fixture(), items=[action(1,"handoff","a"),action(2,"handoff","b")], targets=[];
    f.director.offer(items);f.director.offer(items);
    assert.equal(f.director.queue.length,2);
    const start=JSON.stringify([...f.motion.actors].map(actorTarget));
    for(let i=0;i<1800 && f.director.receipts.length<2;i++) {
        f.director.tick(f.scene,f.views,new Map(),true,i*50,0.05);
        const active=f.director.active;
        if(active?.stage==="perform" && targets.at(-1)!==active.item.target_member_id) targets.push(active.item.target_member_id);
        f.motion.step(0.05);
    }
    assert.deepEqual(targets,["a","b"]);
    assert.deepEqual(Array.from(f.director.receipts,receiptResult),["played","played"]);
    assert.equal(JSON.stringify([...f.motion.actors].map(actorTarget)),start);
    f.director.offer(items);assert.equal(f.director.queue.length,0);
}
/** 因为动作不能改变持久席位，需要提取每个人物最终恢复的逻辑目标。 */
function actorTarget([id,actor]) {
    // 1、只比较身份和锚点，不把插值时钟当业务状态。
    return [id,actor.target.id];
}
/** 因为回执只代表演出结果，需要明确读取 played 或 skipped。 */
function receiptResult(receipt) {
    // 1、不查询模型消息或真实任务状态。
    return receipt.result;
}

/** 因为查历史应去档案库，需要验证到达实体旁、读档动作与原位返回。 */
function verifyArchiveAndPhone() {
    // 1、MCP 只短暂通话，然后后续帧恢复常态，不持续卡在手机。
    const f=fixture();f.director.offer([action(1,"mcp"),action(2,"archive")]);
    let calls=0, reads=0;
    for(let i=0;i<1600 && f.director.receipts.length<2;i++) {
        f.director.tick(f.scene,f.views,new Map(),true,i*50,0.05);
        const hint=f.director.hints.get("lead");
        if(hint?.performance_kind==="mcp") {assert.equal(hint.action,"phone");calls++;}
        if(hint?.performance_kind==="archive") {
            assert.equal(hint.action,"read");
            const pos=f.motion.actors.get("lead").position;
            assert(Math.abs(pos[0]-10)+Math.abs(pos[1]-2.5)<5);reads++;
        }
        f.motion.step(0.05);
    }
    assert(calls>10 && calls<60 && reads>10);
    assert.equal(f.director.receipts.length,2);
}

/** 因为人工答复优先且缺失角色不能堵塞队列，需要检查暂停、恢复和明确跳过。 */
function verifyPauseAndMissingTarget() {
    // 1、等待人工不累计表演时间，也不能生成权限或任务终态。
    const f=fixture();f.director.offer([action(1,"mcp"),action(2,"handoff","removed")]);
    const facts=new Map([["lead",{requires_input:true}]]);
    for(let i=0;i<100;i++)f.director.tick(f.scene,f.views,facts,true,i*50,0.05);
    assert.equal(f.director.active.age,0);
    facts.clear();
    for(let i=0;i<200;i++)f.director.tick(f.scene,f.views,facts,true,5000+i*50,0.05);
    assert.equal(f.director.receipts[0].result,"played");
    assert.equal(f.director.receipts[1].reason,"missing_target");
    f.director.reset();assert.equal(f.director.queue.length,0);assert.equal(f.director.through,0);
}
verifySequentialHandoffs();verifyArchiveAndPhone();verifyPauseAndMissingTarget();
/** 因为一次演出期间可能继续收到重复工具，需要更新汇总次数但保持动作时钟和队列不变。 */
function verifyAggregateUpdatesDoNotReplay() {
    // 1、同一代表项在待播和播放期间更新次数，陈旧快照不能回退统计。
    const f=fixture(),first=action(1,"mcp");
    first.aggregation={version:1,count:1,first_seq:1,last_seq:1,window_ms:60000};
    f.director.offer([first]);
    const next={...first,aggregation:{...first.aggregation,count:3,last_seq:5}};
    f.director.offer([next]);assert.equal(f.director.queue.length,1);
    assert.equal(f.director.queue[0].aggregation.count,3);
    for(let i=0;i<10;i++)f.director.tick(f.scene,f.views,new Map(),true,i*50,0.05);
    const elapsed=f.director.active.elapsed;
    const latest={...first,aggregation:{...first.aggregation,count:8,last_seq:12}};
    f.director.offer([latest]);
    assert.equal(f.director.active.elapsed,elapsed);assert.equal(f.director.queue.length,0);
    f.director.offer([next]);assert.equal(f.director.active.item.aggregation.count,8);
    f.director.tick(f.scene,f.views,new Map(),true,500,0.05);
    const hint=f.director.hints.get("lead");
    assert.equal(hint.aggregation_count,8);assert(hint.caption.includes("8次调用合并"));
    // 2、播完的同一窗口不重新入队，新的代表项仍正常播放。
    for(let i=0;i<100;i++)f.director.tick(f.scene,f.views,new Map(),true,550+i*50,0.05);
    assert.equal(f.director.receipts.length,1);
    f.director.offer([latest]);assert.equal(f.director.queue.length,0);
    f.director.offer([action(2,"handoff","a"),action(3,"handoff","b"),action(20,"mcp")]);
    assert.deepEqual(Array.from(f.director.queue,crewSourceSequence),[2,3,20]);
}
/** 因为合并跨越的来源序号之间仍可能有委派，需要检查播放游标没有跳过这些独立动作。 */
function crewSourceSequence(item) {
    // 1、读取代表序号而非合并组的最后序号。
    return item.source_seq;
}
verifyAggregateUpdatesDoNotReplay();
console.log("Sequential A/B handoffs + archive navigation + brief MCP calls + pause/retry passed");
