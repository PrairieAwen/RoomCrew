/** 因为素材选择必须在真实用户入口生效，需要验证 change、预览、保存、重开与人物渲染。 */
(async function verifyMaterialSelection() {
    // 1、使用正式桥、图集和表单，不注入假角色状态。
    let member;
    const avatar="avatar:27c5734b3cc039323c9fda743e22e089";
    /** 因为导入和绘制异步，需要给实际页面有界推进时间。 */
    function pause(resolve) {
        // 1、不改变角色、缓存或数据库。
        setTimeout(resolve,100);
    }
    /** 因为错误不能静默超时，需要保留素材导入状态和真实提示。 */
    async function until(check) {
        // 1、只观察生产条件，不修改结果使断言成立。
        for(let i=0;i<600;i++){if(await check())return;await new Promise(pause);}
        throw new Error("素材条件超时："+studio.materials.importState+" / "+el("avatar-feedback").textContent);
    }
    /** 因为需要目检真实素材，需要与原生宿主同步截图阶段。 */
    async function capture(stage) {
        // 1、仅导出测试自己的窗口。
        window.__materialSelectionStage=stage;
        await until(captured);
    }
    /** 因为宿主异步导出，需要核对这一阶段实际完成。 */
    function captured() {
        // 1、截图回执不承担任何成员保存权限。
        return window.__materialSelectionCaptured===window.__materialSelectionStage;
    }
    /** 因为选择器是主要入口，需要只发真实 change，而不再额外点击导入按钮。 */
    function select(role) {
        // 1、保存仍由独立明确的用户操作完成。
        el("bundle-character").value=role;
        el("bundle-character").dispatchEvent(new Event("change"));
    }
    /** 因为表单打开后才有预览，需要等待真实应用初始化。 */
    function ready() {
        // 1、所有人物由生产运行时初始化。
        return state.workspace && !state.switching && studio?.data?.members.length;
    }
    /** 因为新角色不能只更新文字，需要检查实际 SVG 和解码后的图集缓存。 */
    function previewReady() {
        // 1、小橘当前为四页显示；不得退回旧人物或内置骨架而宣称导入成功。
        const sprite=studio.materials.view?.sprite;
        return studio.materials.importState==="idle" && el("member-avatar").value===avatar &&
            studio.materials.skins.cache.has(avatar) && sprite?.dataset.variant.startsWith("idle.") &&
            studio.materials.view.spriteId===avatar && !el("save-member").disabled;
    }
    /** 因为保存后应真正更新会议室，需要同时检查正式成员和场景素材引用。 */
    async function saved() {
        // 1、正常刷新不会代替保存或改写成员。
        await studio.refresh();
        member=studio.data.members.find(isTestMember);
        return member?.avatar_id===avatar && !el("member-dialog").open &&
            studio.renderer.views.get(member.id)?.spriteId===avatar;
    }
    /** 因为名称只用于本次合成人物，需要选择测试独有的成员。 */
    function isTestMember(item) {
        // 1、不会查询用户正式资料。
        return item.name==="素材选择验收";
    }
    try {
        await until(ready);studio.addMember();
        el("member-name").value="素材选择验收";el("member-tab-material").click();
        const count=studio.data.members.length;
        select("hippo");
        if(!el("save-member").disabled)throw new Error("加载期间仍能保存旧素材");
        el("member-form").requestSubmit();
        await until(previewReady);
        if((await api("studio_feed",0)).members.length!==count)throw new Error("加载期间误保存成员");
        el("avatar-preview").scrollIntoView({block:"center"});
        await capture("selected-hippo-preview");
        el("save-member").click();studio.roomMode();await until(saved);
        studio.renderer.cameraRig.focus(studio.renderer.motion.actors.get(member.id).position);
        studio.renderer.cameraRig.zoom=1.6;studio.renderer.cameraRig.resize();
        await capture("saved-hippo-scene");
        // 2、重新编辑后连续选择两次，最后一次应胜出；取消选择不能改写正式绑定。
        studio.selected=member.id;await studio.editMember();el("member-tab-material").click();
        await until(previewReady);
        select("owner");select("hippo");await until(previewReady);
        studio.closeMember();await new Promise(pause);
        const retained=await api("member",member.id);
        if(retained.avatar_id!==avatar)throw new Error("取消编辑改写了人物素材");
        window.__materialSelectionResult={ok:true,member_id:member.id,avatar_id:avatar,automaticPreview:true,saveGuard:true,reopened:true,latestWins:true,cancelPreservesBinding:true};
    }catch(error){window.__materialSelectionResult={ok:false,error:String(error),stack:error.stack};}
})();
