const assert = require("node:assert/strict"),
    fs = require("node:fs"),
    vm = require("node:vm");
const context = vm.createContext({ window: {}, structuredClone });
for (const file of [
    "studio/protocol.js",
    "studio/navigation.js",
    "studio/motion.js",
    "studio/assets/scene-v1/catalog.js",
    "studio/scene-assets.js",
    "studio/office-behavior.js",
    "studio/skins.js",
])
    vm.runInContext(fs.readFileSync("desktop/ui/" + file, "utf8"), context);
vm.runInContext("globalThis.classes = {CrewMotion, CrewNavigator, CrewWorkstationDirector, CrewSkins};", context);

/** 因为桌面展示不能让人物背对实际操作对象，需要验证工作、游戏、休闲和人工的朝向区别。 */
function verifyFacing() {
    // 1、旧完成泡泡在新任务执行时不能迫使人物面对用户，电脑游戏也仍面向显示器。
    const actor = {
        phase: "settled",
        direction: "ne",
        target: { purpose: "workstation", direction: "ne" },
    };
    for (const action of ["work", "type", "game", "read"])
        assert.equal(
            context.crewOfficeFacing(
                actor,
                action,
                { activity: "executing", bubble: "旧结果" },
                null,
            ),
            "ne",
        );
    assert.equal(context.crewOfficeFacing(actor, "phone", {}, null), "se");
    assert.equal(
        context.crewOfficeFacing(actor, "work", { requires_input: true }, null),
        "se",
    );
    const player = { heading: 7 };
    const phases = [];
    for (let i = 0; i < 12; i++)
        phases.push(context.crewOfficeTurn(player, actor, "se", 0.05, false));
    assert.equal(phases[0].turning, true);
    assert.ok(phases.some(isSide));
    assert.equal(phases.at(-1).direction, "se");
    assert.equal(phases.at(-1).turning, false);
}

/** 因为背向补帧仅属于显示资源，需要验证原清单、用户帧号和自定义图集不被修改。 */
function verifySupplement() {
    // 1、四套角色保留原清单，只附加八个方向的地面/臀部注册坐姿。
    const catalog = context.window.ROOMCREW_SCENE_ASSETS;
    for (const [id, entry] of Object.entries(catalog.characters)) {
        const manifest = JSON.parse(fs.readFileSync(`desktop/ui/studio/assets/library-v1/characters/${entry.role}/avatar.json`, "utf8"));
        manifest.display_height = 128;
        const before = JSON.stringify(manifest), asset = { id, manifest };
        const sources = ["original0", "original1"], sizes = [[1,1],[1,1]];
        context.crewSceneCharacterSupplement(asset, sources, sizes);
        assert.equal(JSON.stringify(manifest), before);
        assert.equal(sources.length, 6);
        assert.equal(asset.display_manifest.frame_rects.length, manifest.frame_rects.length + 20);
        for(const direction of catalog.directions) {
            const sample = {action:"work", posture:"seated", direction, expression:"neutral", seatMix:1, time:0};
            const clip = context.crewSelectClip(asset.display_manifest, sample);
            assert.equal(clip.direction, direction);
            const actor = {target:{contact:{seat_height:22}}};
            const fit = context.crewSeatContact(asset, actor, sample);
            const pose = asset.display_manifest.frame_rects[clip.frames[0]].contact;
            assert.equal(fit.verified, true);
            assert.ok(Math.abs(pose.hip[1]-fit.elevation+22+fit.pad)<0.0001);
            assert.equal(fit.soleY, pose.soles[1] - fit.elevation);
            assert.equal(fit.support, 0);
            // 2、标准椅采用已配套的完整坐姿；不能把它套到沙发或改过座高的椅子。
            if (["nw", "ne", "sw", "se"].includes(direction)) {
                const pairedSample = {...sample,surface:"workstation",seat_height:22};
                const paired = context.crewSelectClip(asset.display_manifest, pairedSample);
                assert.equal(paired.includes_seat, true);
                assert.equal(asset.display_manifest.frame_rects[paired.frames[0]].page,3);
                assert.equal(context.crewSeatContact(asset,actor,pairedSample).composite,true);
                assert.equal(context.crewSelectClip(asset.display_manifest,{...pairedSample,seat_height:23}).includes_seat,undefined);
                assert.equal(context.crewSelectClip(asset.display_manifest,{...pairedSample,surface:"lounge"}).includes_seat,undefined);
            }
        }
    }
    // 2、所有设备都有八个槽；原绘与旋转对称复用必须明确区分。
    for(const material of Object.values(catalog.materials))
        assert.equal(Object.keys(material.views).length,8);
    const custom = {id:"avatar:custom",manifest:{version:3}};
    assert.equal(context.crewSceneCharacterSupplement(custom, [], []),false);
}
/** 因为过渡应经过侧向而非瞬间翻面，需要判断采样序列中存在侧面。 */
function isSide(value) {
    // 1、侧身仅用于显示过渡。
    return value.direction === "e";
}
/** 因为工作借座不能抢占会议或污染用户原位置，需要验证沙发接单、独占工位和结束回座。 */
function verifyWorkstationBorrowing() {
    // 1、真实位置使用格心，导航仍使用整数；其他椅子只能作为本次路线端点。
    const { CrewMotion, CrewNavigator, CrewWorkstationDirector } = context.classes;
    const nav = new CrewNavigator();
    nav.update({ version: 1, revision: 1, width: 10, height: 10, blocked: [], seats: [[2, 2], [4, 2], [6, 2]] });
    assert.equal(nav.free([4, 2]), false);
    const path = nav.route([2, 2], [6, 2]);
    assert.ok(path.length > 0);
    assert.ok(!path.slice(1, -1).some(isMiddleChair));
    const motion = new CrewMotion();
    const sofa = { id: "sofa", approach: [2, 2], position: [2.5, 2.5], posture: "seated", purpose: "lounge" };
    const desk = { id: "desk", approach: [6, 2], position: [6.5, 2.5], posture: "seated", purpose: "workstation", direction: "nw" };
    const scene = { anchors: [sofa, desk], placements: [{ member_id: "a", anchor_id: "sofa" }] };
    motion.restore({ member_id: "a", anchor_id: "sofa", generation: 1 }, scene.anchors, 1);
    const director = new CrewWorkstationDirector(motion, nav);
    const views = new Map([["a", { member: { role: "assistant" } }]]);
    const facts = new Map([["a", { active_contexts: 1, activity: "executing" }]]);
    director.tick(scene, views, facts, new Set(["a"]));
    assert.equal(motion.actors.get("a").target.id, "sofa");
    director.tick(scene, views, facts, new Set());
    const actor = motion.actors.get("a");
    assert.equal(actor.target.id, "desk");
    assert.equal(actor.visualHome.id, "sofa");
    for (let i = 0; i < 100; i++) motion.step(0.05);
    assert.equal(actor.posture, "seated");
    assert.equal(actor.direction, "nw");
    assert.equal(context.crewOfficeAction(actor, "work"), "work");
    facts.clear();
    director.tick(scene, views, facts, new Set());
    for (let i = 0; i < 100; i++) motion.step(0.05);
    assert.equal(actor.target.id, "sofa");
    assert.equal(context.crewOfficeAction(actor, "type"), "think");
    assert.equal(context.crewOfficeAction(actor, "game"), "phone");
    assert.equal(actor.generation, 1);
    // 2、坐姿抬升随起坐连续变化；正面绑定不能破坏电脑工作朝向。
    const sample = { action: "work", posture: "seated", direction: "nw", surface: "workstation" };
    assert.equal(context.crewOfficeBindingCompatible({ action: "work", clip: "work.se.seated.neutral" }, sample), false);
    assert.equal(context.crewOfficeBindingCompatible({ action: "work", clip: "work.ne.seated.neutral" }, sample), false);
    assert.equal(context.crewOfficeBindingCompatible({ action: "work", clip: "work.nw.seated.neutral" }, sample), true);
}
/** 因为路线只能离开与进入目标椅子，需要识别不应穿越的中间椅子。 */
function isMiddleChair(point) {
    // 1、不把端点特许扩展到整条路线。
    return point[0] === 4 && point[1] === 2;
}

/** 因为离座绑定原椅、落座绑定新椅，需要验证配套片段的来源、脚点交接和自定义素材回退。 */
function verifyStandardChairExchange() {
    // 1、使用不同位置、不同方向的两个标准座位，防止错误复用旧座椅退出点仍然通过。
    const motion = new context.classes.CrewMotion();
    motion.presetMembers.set("a", [-23, -1]);
    const source = {id:"source",position:[2.8,2.5],approach:[3,2],posture:"seated",purpose:"workstation",direction:"nw",contact:{seat_height:22}};
    const target = {id:"target",position:[5.8,2.5],approach:[6,2],posture:"seated",purpose:"workstation",direction:"ne",contact:{seat_height:22}};
    motion.restore({member_id:"a",anchor_id:"source",generation:1},[source,target],1);
    const actor = motion.actors.get("a");
    motion.visualMove("a", [[3,2],[4,2],[5,2],[6,2]], target, "work");
    assert.equal(context.crewAttachedSeat(actor).id,"source");
    let previous = context.crewActorFootPosition(actor), maximum = 0;
    for(let i=0;i<200;i++) {
        motion.step(0.025);
        const current=context.crewActorFootPosition(actor);
        maximum=Math.max(maximum,Math.hypot(current[0]-previous[0],current[1]-previous[1]));
        previous=current;
        if(actor.phase==="stand_up") assert.equal(context.crewAttachedSeat(actor).id,"source");
        if(actor.phase==="sit_down") assert.equal(context.crewAttachedSeat(actor).id,"target");
    }
    assert.equal(actor.phase,"settled");
    assert.ok(maximum<0.3,"鞋底交接不能通过更换定位原点产生跳位");
    assert.deepEqual(Array.from(motion.chairs.get("target")),target.position);
    assert.notDeepEqual(Array.from(motion.chairs.get("source")),source.position);
    // 2、离座中再次改目的地只换后续路线，不能跳成站立或绑定到刚选的新椅子。
    const nextPlan = {member_id:"a",generation:2,scene_revision:1,plan_id:"switch-1",mode:"presentation_only",route:[[6,2],[5,2],[4,2],[3,2]],source:target,target:source};
    assert.equal(motion.accept(nextPlan),true);
    for(let i=0;i<4;i++)motion.step(0.025);
    const before = motion.actors.get("a"), footBefore = context.crewActorFootPosition(before);
    assert.equal(motion.accept({...nextPlan,generation:3,plan_id:"switch-2"}),true);
    const after = motion.actors.get("a");
    assert.equal(after.phase,before.phase);
    assert.equal(after.progress,before.progress);
    assert.equal(after.sourceSeat.id,"target");
    assert.deepEqual(Array.from(context.crewActorFootPosition(after)),Array.from(footBefore));
    // 3、每个方向的作者鞋底经投影后应落在导航格心，检查真实 24/12 投影的逆变换。
    for(const direction of ["nw","ne"]) {
        const exit=context.crewSeatExit(source,direction,actor);
        const projected=context.crewProject(exit), offset=context.crewSeatFootOffset(actor,direction);
        const approach=context.crewProject([3.5,2.5]);
        assert.ok(Math.abs(projected[0]+offset[0]-approach[0])<1e-8);
        assert.ok(Math.abs(projected[1]+offset[1]-approach[1])<1e-8);
    }
    // 4、没有匹配配套资源的自定义人物不使用椅脚定位，也不污染椅子的滚动记录。
    const custom = new context.classes.CrewMotion();
    custom.restore({member_id:"custom",anchor_id:"source",generation:1},[source,target],1);
    custom.visualMove("custom",[[3,2],[4,2],[5,2],[6,2]],target,"work");
    for(let i=0;i<200;i++)custom.step(0.025);
    assert.equal(custom.chairs.size,0);
    assert.equal(custom.actors.get("custom").phase,"settled");
}

const imageDimensions = new Map();
class DecodedTestImage {
    /** 因为本测试验证来源装配而不是浏览器解码，需要登记该图片将返回的真实合同尺寸。 */
    set src(value) {
        // 1、所有尺寸仅来自本地目录，不访问网络或依赖 DOM。
        this.dimensions = imageDimensions.get(value);
    }
    /** 因为生产加载器会等待图片完成，需要模拟解码边界并拒绝没有登记的来源。 */
    async decode() {
        // 1、未知补图不能因为测试替身而被默许加载。
        assert.ok(this.dimensions);
        [this.naturalWidth, this.naturalHeight] = this.dimensions;
    }
}

/** 因为补图加载曾被单页白名单拒绝，需要走完整 ensure 并检查六个显示页和原数组不变。 */
async function verifyDisplayPageLoading() {
    // 1、替身只代替 Image 解码，仍调用正式加载器与正式方向素材合同。
    context.Image = DecodedTestImage;
    const catalog = context.window.ROOMCREW_SCENE_ASSETS;
    for (const [id, entry] of Object.entries(catalog.characters)) {
        const manifest = JSON.parse(fs.readFileSync(`desktop/ui/studio/assets/library-v1/characters/${entry.role}/avatar.json`, "utf8"));
        manifest.display_height = 128;
        const sources = ["data:image/png;base64,AAAA", "data:image/png;base64,BBBB"];
        manifest.atlas_sizes = [];
        for (const file of manifest.images) {
            const png = fs.readFileSync(`desktop/ui/studio/assets/library-v1/characters/${entry.role}/${file}`);
            manifest.atlas_sizes.push([png.readUInt32BE(16),png.readUInt32BE(20)]);
        }
        const asset = {id,manifest,image_pages:sources};
        for (let i=0;i<2;i++) imageDimensions.set(sources[i],manifest.atlas_sizes[i]);
        imageDimensions.set(entry.image,entry.size);
        imageDimensions.set(entry.paired.image,entry.paired.size);
        imageDimensions.set(entry.transition.image,entry.transition.size);
        imageDimensions.set(entry.call.image,entry.call.size);
        const before = JSON.stringify({manifest,sources});
        const skins = new context.classes.CrewSkins(loadTestAsset.bind(null,asset));
        skins.ensure(id);
        await skins.pending.get(id);
        assert.equal(skins.errors.size,0);
        assert.equal(skins.cache.get(id).decoded_pages.length,6);
        assert.equal(JSON.stringify({manifest,sources}),before);
    }
    console.log("six display pages + private supplement allowlist + immutable source arrays passed");
}

/** 因为正式加载器接收异步素材入口，需要返回本测试构造的清单而不绕过 ensure。 */
async function loadTestAsset(asset) {
    // 1、保留原对象引用，用于发现对用户清单的意外修改。
    return asset;
}

/** 因为异步断言不能被 Node 当作未观察 Promise，需要让失败明确改变测试进程退出码。 */
function failDisplayPageLoading(error) {
    // 1、只输出合成测试断言，不包含用户数据。
    console.error(error);
    process.exitCode = 1;
}
verifyFacing();
verifySupplement();
verifyWorkstationBorrowing();
verifyStandardChairExchange();
verifyDisplayPageLoading().catch(failDisplayPageLoading);
console.log(
    "office orientation + seated turn + immutable builtin supplements + custom asset isolation passed",
);
