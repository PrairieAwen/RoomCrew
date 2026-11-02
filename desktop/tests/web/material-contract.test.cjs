const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),cp=require("node:child_process");
const context=vm.createContext({window:{},structuredClone});
for(const file of ["protocol.js","assets/library-v1/catalog.js","assets/scene-v1/catalog.js",
    "assets/library-v1/characters/hippo/display.js","material-contract.js","scene-assets.js"])
    vm.runInContext(fs.readFileSync("desktop/ui/studio/"+file,"utf8"),context);

/** 因为渲染校准依赖真实导入几何，需要使用生产注册器读取原始 PNG，而非手写期望数据。 */
function loadAssets() {
    // 1、子进程仅分析项目内公开素材，不访问模型、网络或用户资料。
    const script=`
import json
from pathlib import Path
from roomcrew_desktop.assets.registration import register_frames
result=[]
for folder in Path('desktop/ui/studio/assets/library-v1/characters').iterdir():
    m=json.loads((folder/'avatar.json').read_text('utf-8'));m['display_height']=128
    pages=[(folder/name).read_bytes() for name in m['images']]
    result.append(dict(role=folder.name,manifest=m,registration=register_frames(m,pages)))
print(json.dumps(result))
`;
    const output=cp.spawnSync(".venv/Scripts/python.exe",["-c",script],{encoding:"utf8",
        env:{...process.env,PYTHONPATH:"desktop/src",PYTHONIOENCODING:"utf-8"}});
    assert.equal(output.status,0,output.stderr);
    return JSON.parse(output.stdout);
}

/** 因为尺寸标准应兼顾稳定步态、短体型和用户自制，需要验证实际装配后的片段、源数据和边界。 */
function verifyCalibration() {
    // 1、同一套真实导入结果进入正式显示补页，原图清单和原几何都必须保持不变。
    const catalog=context.window.ROOMCREW_MATERIAL_LIBRARY.characters;
    for(const asset of loadAssets()) {
        asset.id=catalog.find(matchesRole,asset.role).registered_id;
        const original=JSON.stringify({manifest:asset.manifest,registration:asset.registration});
        context.crewSceneCharacterSupplement(asset,["source0","source1"],[[1,1],[1,1]]);
        assert.equal(JSON.stringify({manifest:asset.manifest,registration:asset.registration}),original);
        const m=asset.manifest,unit=128/m.frame_size[1],frames=asset.display_registration.frames;
        // 2、人类每段步态共享倍率，站立和行走体量一致；跑步保留合理屈膝而非拉成长站姿。
        if(asset.role!=="hippo") {
            const transition=context.window.ROOMCREW_SCENE_ASSETS.characters[asset.id].transition;
            const reference=transition.standing_foot[1]-(transition.frames.at(-1).offset[1]-m.pivot[1])*unit;
            for(const clip of m.clips) {
                if(clip.posture!=="standing" || clip.expression!=="neutral" ||
                    !["idle","walk","run"].includes(clip.action))continue;
                const heights=clip.frames.map(frameHeight,{m,frames,unit});
                assert.ok(Math.abs(context.crewMaterialMedian(heights)-reference*(clip.action==="run"?0.91:1))<0.001,asset.role+":"+clip.action+":"+clip.direction+" "+context.crewMaterialMedian(heights)+" / "+reference);
                const scales=clip.frames.map(frameScale,frames);
                assert.ok(Math.max(...scales)-Math.min(...scales)<0.000001,asset.role+":"+clip.action+":"+clip.direction+" "+scales.join(","));
            }
        } else {
            for(let i=0;i<m.frame_rects.length;i++)assert.equal(frames[i].scale,m.frame_rects[i].scale);
        }
        assert.ok(context.crewMaterialCoverage(asset).includes("非完整美术验收"));
        // 3、冒用官方名称的自定义内容不能触发内置体型覆盖或私有补页。
        const custom={id:"avatar:user-defined",manifest:structuredClone(m),registration:structuredClone(asset.registration)};
        assert.equal(context.crewSceneCharacterSupplement(custom,[],[]),false);
        assert.equal(custom.display_registration,undefined);
    }
}

/** 因为目录顺序可能变化，需要按稳定角色标识寻找对应受信内容。 */
function matchesRole(item) {
    // 1、角色名称不参与内容校准授权。
    return item.id===String(this);
}
/** 因为身高验收必须使用实际显示尺度，需要将源矩形换算为世界单位。 */
function frameHeight(index) {
    // 1、不把原图留白计入人物身高。
    return this.m.frame_rects[index].rect[3]*this.frames[index].scale*this.unit;
}
/** 因为动作内不能变焦，需要读取每帧最终采用的固定缩放。 */
function frameScale(index) {
    // 1、作者图集和显示校准仍分别保存。
    return this[index].scale;
}
verifyCalibration();
console.log("Real atlases: fixed clip scale, coherent humanoid size, mascot/custom isolation and immutable sources passed");
