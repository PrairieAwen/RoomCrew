/** 因为演出可以晚于真实执行，需要验证两个已完成子任务仍按来源顺序递交文件。 */
(async function verifyQueuedPerformance() {
    // 1、按正式页面入口提交，摄像机只用于检查画面，不改变任务或动作数据。
    const order = [], captured = new Set();
    let before, firstConversation, finishedBeforePlayback = false;
    /** 因为执行和移动是独立异步流程，需要在观察间释放浏览器帧循环。 */
    function pause(resolve) {
        // 1、只控制验收采样频率。
        setTimeout(resolve,100);
    }
    /** 因为条件可能永远不成立，需要明确超时并保留阶段。 */
    async function until(check) {
        // 1、不修改真实状态来让断言通过。
        for(let i=0;i<1200;i++) {if(await check()) return; await new Promise(pause);}
        throw new Error("performance timeout: "+window.__performanceStage);
    }
    /** 因为截图应包含实际递文件或翻页，需要等自己窗口的原生导出。 */
    async function capture(name) {
        // 1、没有读取其他应用的桌面画面。
        window.__performanceStage=name;
        await until(captureReady);
    }
    /** 因为宿主和页面独立运行，需要核对截图导出回执。 */
    function captureReady() {
        // 1、不伪造图像完成。
        return window.__performanceCaptured===window.__performanceStage;
    }
    /** 因为刷新要同时消费回执，需要用正式控制器持续推进。 */
    async function allConsumed() {
        // 1、真实执行已结束不能让未播事件消失。
        await studio.refresh();
        const current=studio.renderer.collaboration.active;
        if(current?.stage==="perform" && current.elapsed>0.4) {
            const item=current.item;
            if(item.kind==="handoff" && !captured.has(item.id)) {
                captured.add(item.id);order.push(item.target_member_id);
                const actor=studio.renderer.motion.actors.get(item.member_id);
                studio.renderer.cameraRig.focus(actor.position);
                studio.renderer.cameraRig.zoom=1.2;studio.renderer.cameraRig.resize();
                if(studio.renderer.performanceEffects.group.dataset.kind!=="handoff") throw new Error("递交文件道具未显示");
                await capture("handoff-"+order.length);
            } else if(item.kind==="archive" && !captured.has(item.id)) {
                captured.add(item.id);
                const actor=studio.renderer.motion.actors.get(item.member_id);
                studio.renderer.cameraRig.focus(actor.position);
                studio.renderer.cameraRig.zoom=1.2;studio.renderer.cameraRig.resize();
                if(actor.target.purpose!=="performance" || studio.renderer.performanceEffects.group.dataset.kind!=="archive") throw new Error("未到档案库翻查");
                await capture("archive-lookup");
            }
        }
        return studio.data.actions_pending===0 && !current && !studio.renderer.collaboration.queue.length;
    }
    /** 因为终态只能来自框架，需要查询真实活动 Run 而非动画结束。 */
    async function backendFinished() {
        // 1、不等待表演，验证执行在视觉消费前已经正常返回。
        const overview=await api("overview");renderOverview(overview);
        return !overview.active_run && !overview.active_runs?.length;
    }
    /** 因为人物素材与布局异步加载，需要等待完整的正式快照。 */
    function ready() {
        // 1、两个同事由测试用户入口实际创建。
        return state.workspace && !state.switching && studio?.renderer?.views.size===4;
    }
    try {
        await until(ready);
        before=JSON.stringify(studio.data.scene.placements);
        await newConversation();firstConversation=state.conversation.id;
        el("prompt").value="同时派两个已经配置的同事工作";
        await sendTask({preventDefault:preventSubmit});studio.roomMode();
        await until(backendFinished);
        finishedBeforePlayback=studio.renderer.collaboration.queue.length>0 || Boolean(studio.renderer.collaboration.active);
        await until(allConsumed);
        const events=await api("events",firstConversation,0);
        const expected=events.filter(isAssigned).map(assignmentTarget);
        if(order.length!==2 || JSON.stringify(order)!==JSON.stringify(expected)) throw new Error("并行委派未按来源先后消费");
        if(JSON.stringify(studio.data.scene.placements)!==before) throw new Error("演出改写了持久席位");
        // 2、历史检索也走真实工具，再等待已经结束的工具行为走到档案库演示。
        await newConversation();el("prompt").value="去档案库查一次合成历史";
        await sendTask({preventDefault:preventSubmit});studio.roomMode();
        await until(backendFinished);await until(allConsumed);
        window.__performanceResult={ok:true,order,finishedBeforePlayback,seatsUnchanged:true,archiveVisited:window.__performanceStage==="archive-lookup"};
    } catch(error) {window.__performanceResult={ok:false,error:String(error),stack:error.stack,order};}
    /** 因为委派来源不能靠名字猜测，需要只选择正式已配置委派事件。 */
    function isAssigned(event) {
        // 1、模型文本和普通工具事件不算成员派发。
        return event.kind==="task.assigned" && event.payload.delegation_kind==="configured";
    }
    /** 因为期望顺序来自事件日志，需要保留实际成员身份。 */
    function assignmentTarget(event) {
        // 1、不以头像或 Agent 定义 ID 合并不同人物。
        return event.payload.target_member_id;
    }
    /** 因为正式发送入口接收表单事件，需要提供阻止页面刷新的具名回调。 */
    function preventSubmit() {
        // 1、不会影响执行器。
    }
})();
