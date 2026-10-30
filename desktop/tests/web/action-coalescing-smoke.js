/** 因为合并演出不能合并真实工具调用，需要在正式会话中验证多次 MCP 与档案查询。 */
(async function verifyActionCoalescing() {
    // 1、任务走真实用户入口，动作由正式队列消费，不向渲染器注入事件。
    const played=new Map(),capturedKinds=new Set();
    let placements,first;
    /** 因为工具和运动异步，需要把控制权交回帧循环。 */
    function pause(resolve) {
        // 1、只控制验证采样频率，不改变合并时钟。
        setTimeout(resolve,100);
    }
    /** 因为条件可能永远不满足，需要有界失败并报告真实进度。 */
    async function until(check) {
        // 1、不修改模型状态或队列来满足断言。
        for(let i=0;i<1200;i++){if(await check())return;await new Promise(pause);}
        throw new Error("合并验收超时："+window.__coalescingStage);
    }
    /** 因为需要目检合并次数提示，需要与原生截图导出握手。 */
    async function capture(kind) {
        // 1、只导出本验证窗口，不读取用户其他应用。
        window.__coalescingStage=kind;
        await until(captureDone);
    }
    /** 因为截图导出异步，需要确认当前阶段已经落盘。 */
    function captureDone() {
        // 1、回执不会确认播放或修改工具结果。
        return window.__coalescingCaptured===window.__coalescingStage;
    }
    /** 因为执行和演出顺序独立，需要每轮通过正式快照推进并观察实际导演。 */
    async function drained() {
        // 1、同一代表项只统计一次，计数来自实际聚合数据。
        await studio.refresh();
        const active=studio.renderer.collaboration.active;
        if(active?.stage==="perform" && active.elapsed>0.4) {
            const item=active.item;
            played.set(item.id,item.kind);
            if(!capturedKinds.has(item.kind)) {
                capturedKinds.add(item.kind);
                const hint=studio.renderer.collaboration.hints.get(item.member_id);
                if((item.aggregation?.count||1)<2 || !hint?.caption.includes("次调用合并"))
                    throw new Error("重复调用未聚合或次数提示未更新");
                studio.renderer.cameraRig.focus(studio.renderer.motion.actors.get(item.member_id).position);
                studio.renderer.cameraRig.zoom=1.4;studio.renderer.cameraRig.resize();
                await capture(item.kind);
            }
        }
        const overview=await api("overview");renderOverview(overview);
        return !overview.active_run && !overview.active_runs?.length && !active &&
            !studio.data.actions_pending && !studio.renderer.collaboration.queue.length;
    }
    /** 因为第一条工具事件应在初始基线之后，需要先等待空间已加载。 */
    function ready() {
        // 1、初始化来自生产运行时。
        return state.workspace && !state.switching && studio?.data?.scene && !studio.data.catching_up;
    }
    /** 因为正式提交入口接收表单事件，需要具名阻止默认提交回调。 */
    function preventDefault() {
        // 1、不绕过任务准入或模型执行。
    }
    /** 因为原始轨迹必须完整，需要统计事件类型而不依赖最终模型文字。 */
    function isMCP(event) {
        // 1、按正式工具类别识别。
        return event.kind==="tool.started" && event.payload.tool_kind==="mcp";
    }
    /** 因为档案查询合并后仍应逐次执行，需要统计真实工具开始事件。 */
    function isArchive(event) {
        // 1、这里只包含本轮实际发起的固定查询工具。
        return event.kind==="tool.started" && event.payload.name==="search_archive";
    }
    try {
        await until(ready);placements=JSON.stringify(studio.data.scene.placements);
        await newConversation();first=state.conversation.id;
        el("prompt").value="连续调用八次 MCP 和六次档案查询";
        await sendTask({preventDefault});studio.roomMode();await until(drained);
        if(played.size!==2)throw new Error("首轮没有压缩为一次电话和一次查档往返");
        const before=[...played.keys()];
        // 2、首轮演出已经播完，同一分钟内第二个 Run 的调用仍归入已播组，不再来回跑。
        await newConversation();const second=state.conversation.id;
        el("prompt").value="继续调用两次 MCP 和两次档案查询";
        await sendTask({preventDefault});studio.roomMode();await until(drained);
        const events=[...(await api("events",first,0)),...(await api("events",second,0))];
        const mcp=events.filter(isMCP).length,archive=events.filter(isArchive).length;
        if(mcp!==10 || archive!==8)throw new Error("真实工具轨迹被合并或缺失");
        if(played.size!==2 || JSON.stringify([...played.keys()])!==JSON.stringify(before))
            throw new Error("已播窗口又触发重复动画");
        if(JSON.stringify(studio.data.scene.placements)!==placements)throw new Error("聚合修改了成员工位");
        window.__coalescingResult={ok:true,sourceMCP:mcp,sourceArchive:archive,visualActions:played.size,
            secondRunDidNotReplay:true,coalesced:studio.data.actions_coalesced,seatsUnchanged:true};
    }catch(error){window.__coalescingResult={ok:false,error:String(error),stack:error.stack,visualActions:played.size};}
})();
