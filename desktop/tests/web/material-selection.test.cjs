/* 素材选择异步竞态、加载期间保存和失败恢复。 */
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");

/** 因为竞态需要精确控制返回顺序，需要用最小表单节点运行实际素材逻辑。 */
function fixture() {
    // 1、仅替代 DOM 与桥传输，导入状态机和保存准入使用生产实现。
    const fields=new Map(),requests=[],toasts=[];
    /** 因为本测试不渲染图像，需要保存实际方法使用的有限表单属性。 */
    function field(id) {
        // 1、节点相互独立，不把两个下拉框的值混在一起。
        if(!fields.has(id))fields.set(id,{value:"",disabled:false,open:true,textContent:"",append,replaceChildren,dispatchEvent});
        return fields.get(id);
    }
    /** 因为目录会逐项填入选择框，需要提供不改变业务数据的节点接口。 */
    function append() {
        // 1、具体选中值由生产方法显式设置。
    }
    /** 因为刷新目录应清理旧选择，需要模拟原生 select 的重建。 */
    function replaceChildren() {
        // 1、不替生产方法选择新的角色。
        this.value="";
    }
    /** 因为素材切换会通知动作编辑器，需要在本隔离测试中保留事件边界。 */
    function dispatchEvent() {
        // 1、动作编辑器的实际更新由原生联合验收覆盖。
    }
    /** 因为后端响应可以颠倒，需要将每个桥请求交给测试逐项完成。 */
    function api(method,...args) {
        // 1、不修改生产请求的方法和参数。
        const request={method,args};requests.push(request);
        /** 因为测试要模拟迟到的目录结果，需要保留当前 Promise 的完成入口。 */
        function capture(resolve,reject) {
            // 1、每次请求都有自己的完成入口。
            request.resolve=resolve;request.reject=reject;
        }
        return new Promise(capture);
    }
    /** 因为本测试只检查目录选择，需要创建不带 HTML 的选项占位。 */
    function node() {
        // 1、不模拟图片成功或框架执行结果。
        return {value:""};
    }
    /** 因为加载期间误提交应给用户提示，需要记录实际控制层的阻止原因。 */
    function toast(message) {
        // 1、不自动清空或改写表单。
        toasts.push(message);
    }
    /** 因为已注册图像不需本测试解码，需要只保留图片缓存边界。 */
    function ensure() {
        // 1、原生验收会验证真实 PNG 解码和场景绘制。
    }
    const context=vm.createContext({el:field,api,node,toast,Event});
    vm.runInContext(fs.readFileSync("desktop/ui/studio/materials.js","utf8")+fs.readFileSync("desktop/ui/studio/controller.js","utf8")+";globalThis.subject={CrewMaterialPanel,CrewStudio};",context);
    const panel=Object.create(context.subject.CrewMaterialPanel.prototype);
    Object.assign(panel,{token:0,importState:"idle",saving:false,skins:{pending:new Map(),cache:new Map(),errors:new Set(),ensure}});
    field("member-avatar").value="avatar:old";
    field("bundle-character").value="hippo";
    return {panel,field,requests,toasts,studio:context.subject.CrewStudio};
}

/** 因为目录刷新也会迟到，需要在 A 的目录未返回时完成 B 并确认最新选择胜出。 */
async function verifyLatestSelectionAndSaveGuard() {
    // 1、加载中即便绕过 disabled 提交表单，也不能保存旧人物。
    const f=fixture(),first=f.panel.importSource("import_avatar_bundle","owner");
    assert(f.field("save-member").disabled);
    await f.studio.prototype.saveMember.call({materials:f.panel},{preventDefault});
    assert.equal(f.requests.length,1);assert.equal(f.toasts.length,1);
    f.requests[0].resolve({id:"avatar:old"});await flush();
    const latest=f.panel.importSource("import_avatar_bundle","hippo");
    f.requests[2].resolve({id:"avatar:new"});await flush();
    f.panel.skins.cache.set("avatar:new",{});
    f.requests[3].resolve([{id:"avatar:new",name:"小橘"}]);await latest;
    // 2、旧目录再返回不能覆盖新预览，也不能错误解锁新请求的按钮。
    f.requests[1].resolve([{id:"avatar:old",name:"旧人物"}]);await first;
    assert.equal(f.field("member-avatar").value,"avatar:new");
    assert.equal(f.panel.importState,"idle");assert.equal(f.field("save-member").disabled,false);
}

/** 因为失败不能表现为旧人物已应用，需要阻止保存并允许明确重载恢复。 */
async function verifyFailureAndRetry() {
    // 1、注册成功但解码失败时仍保持错误，不能把骨架回退当作新素材预览成功。
    const f=fixture(),pending=f.panel.importSource("import_avatar_bundle","hippo");
    f.requests[0].resolve({id:"avatar:new"});await flush();
    f.requests[1].resolve([{id:"avatar:new",name:"小橘"}]);await pending;
    assert.equal(f.panel.importState,"failed");assert(f.field("save-member").disabled);
    /** 因为重新加载应能解除失败状态，需要模拟这一次真实解码成功。 */
    function recover(id) {
        // 1、只改变缓存结果，不覆盖生产状态机。
        f.panel.skins.cache.set(id,{});
    }
    f.panel.skins.ensure=recover;await f.panel.reload();
    assert.equal(f.panel.importState,"idle");assert.equal(f.field("save-member").disabled,false);
}

/** 因为关闭后的导入可能完成，需要保证它不改变已关闭或下一次打开的表单。 */
async function verifyClosedFormIgnoresLateImport() {
    // 1、关闭失效令牌，迟到注册只保留在素材库，不自动绑定成员。
    const f=fixture(),pending=f.panel.importSource("import_avatar_bundle","hippo");
    f.panel.close();f.field("member-dialog").open=false;
    f.requests[0].resolve({id:"avatar:new"});await pending;
    assert.equal(f.field("member-avatar").value,"avatar:old");assert.equal(f.requests.length,1);
}

/** 因为实际保存入口会阻止默认提交，需要提供具名表单回调。 */
function preventDefault() {
    // 1、不读取或写入任何账号库。
}
/** 因为跨 VM 的 Promise 需要完成异步采纳，需要让出一轮事件循环后再检查新请求。 */
async function flush() {
    // 1、不使用固定睡眠或修改生产请求来控制返回顺序。
    await new Promise(setImmediate);
}
/** 因为竞态用例是异步的，需要串行验证并明确传播失败。 */
async function main() {
    // 1、覆盖最新选择、保存准入和关闭后的迟到返回。
    await verifyLatestSelectionAndSaveGuard();await verifyFailureAndRetry();await verifyClosedFormIgnoresLateImport();
    console.log("Material selection: latest wins, save guard, decode retry and close invalidation passed");
}
/** 因为 Node 异步异常必须使回归失败，需要设置非零退出码。 */
function fail(error) {
    // 1、只输出本测试的合成断言。
    console.error(error);process.exitCode=1;
}
main().catch(fail);
