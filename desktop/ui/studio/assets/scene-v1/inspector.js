"use strict";
const sceneCatalog = window.ROOMCREW_SCENE_ASSETS;
const directionNames = {e:"东",se:"东南",s:"南",sw:"西南",w:"西",nw:"西北",n:"北",ne:"东北"};

/** 因为外部素材名称不能执行 HTML，需要只创建文本节点。 */
function entryNode(tag, text = "") {
    // 1、所有内容以文本呈现，不拼接任意 HTML。
    const element = document.createElement(tag); element.textContent = text; return element;
}

/** 因为多次切换可能迟到，需要只在当前卡片仍连接时绘制本地 PNG。 */
async function renderSceneAsset(entry, direction, card, isPerson) {
    // 1、路径来自随包目录，不接受模型生成的 URL。
    const canvas = card.querySelector("canvas"), context = canvas.getContext("2d");
    const frame = isPerson ? (entry.previewIncludesSeat
        ? entry.frames[Math.min(entry.frames.length - 1, Number(document.getElementById("frame").value))]
        : entry.frames.find(matchesDirection, direction)) : entry.views[direction];
    const image = new Image(); image.src = isPerson
        ? "../" + entry.image.split("/").slice(2).join("/")
        : "../library-v1/" + (frame.image || entry.image);
    await image.decode(); if (!canvas.isConnected) return;
    const [x,y,w,h] = frame.rect, scale = Math.min(240/w,170/h), left = (280-w*scale)/2, top = 180-h*scale;
    context.drawImage(image,x,y,w,h,left,top,w*scale,h*scale);
    // 2、标记真实登记的髋部与地面基线，供作者检查原图而不是看动画标签猜测。
    if (isPerson && document.getElementById("markers").checked) {
        const unit = 128/entry.virtual_size[1];
        const rootX = (entry.pivot[0]-frame.offset[0])/frame.scale;
        if (entry.previewIncludesSeat) {
            const rootY = (entry.pivot[1] - frame.offset[1]) / frame.scale;
            markPoint(context, left + rootX * scale, top + rootY * scale, "#2673d0");
        } else {
            markPoint(context,left+rootX*scale,top+(h-frame.contact.seat_height/(frame.scale*unit))*scale,"#1c9765");
            const soleX = rootX + frame.contact.soles[0] / (frame.scale * unit);
            markPoint(context,left+soleX*scale,top+h*scale,"#2673d0");
        }
    }
}

/** 因为目录以方向作为稳定键，需要精确查找对应原绘帧。 */
function matchesDirection(frame) {
    // 1、不通过最接近图片冒充该方向已经存在。
    return frame.direction === String(this);
}

/** 因为接触标记要明显区别于原画，需要只在预览画布叠加彩色圆点。 */
function markPoint(context,x,y,color) {
    // 1、不会把标记写回 PNG 或用于执行状态。
    context.fillStyle=color;context.beginPath();context.arc(x,y,4,0,Math.PI*2);context.fill();
}

/** 因为设备与人物共享方向但合同不同，需要按当前选择重建只读预览。 */
function refreshSceneInspector() {
    // 1、画布只保留当前类别，图片完成后检查节点是否仍有效。
    const kind=document.getElementById("kind").value, direction=document.getElementById("direction").value;
    const grid=document.getElementById("grid");grid.replaceChildren();
    const people=kind!=="furniture", entries=people?sceneCatalog.characters:sceneCatalog.materials;
    document.getElementById("frame").disabled = !["paired", "transition"].includes(kind);
    document.getElementById("frame").max = kind === "paired" ? 3 : 5;
    for(const [id,source] of Object.entries(entries)) {
        const entry = source[kind] ? {...source, ...source[kind], previewIncludesSeat:true} : source;
        const card=entryNode("article");card.className="card";
        card.append(entryNode("strong",people?entry.name:sceneCatalog.definitions[id].label));
        const canvas=document.createElement("canvas");canvas.width=280;canvas.height=200;card.append(canvas);
        card.append(entryNode("div", people ? kind === "paired"
            ? "待命 / 打字 A / 打字 B / 正面 · 蓝点为椅脚根点"
            : kind === "transition" ? "六张连续起坐关键帧 · 蓝点为椅脚根点"
            : "旧八向坐姿参考 · 接触标记仍需精修"
            : entry.views[direction].camera_profile_id ? "统一 2:1 重制 · 方向关键帧"
            : entry.views[direction].coverage === "drawn" ? "历史方向关键帧"
            : entry.views[direction].coverage === "symmetric" ? "旋转对称复用" : "历史单向资源"));
        grid.append(card);renderSceneAsset(entry,direction,card,people).catch(showAssetFailure.bind(null,card));
    }
}

/** 因为损坏图片不能伪装成功，需要在对应卡片显示读取失败。 */
function showAssetFailure(card,error) {
    // 1、不泄露宿主路径或配置。
    console.error("RoomCrew local asset preview failed", error);
    card.append(entryNode("p","该素材预览读取失败"));
}

/** 因为素材页在受限 iframe 中运行，需要只发送有限的关闭请求。 */
function closeSceneInspector() {
    // 1、独立打开时不关闭用户浏览器。
    if(window.parent!==window)window.parent.postMessage({type:"roomcrew.material.close"},"*");
}
for(const direction of sceneCatalog.directions){const option=entryNode("option",directionNames[direction]);option.value=direction;document.getElementById("direction").append(option);}
document.getElementById("direction").value="se";
for(const id of ["kind","direction","markers","frame"])document.getElementById(id).addEventListener("change",refreshSceneInspector);
document.getElementById("close").addEventListener("click",closeSceneInspector);
for(const [kind,entry] of Object.entries(sceneCatalog.materials)){const row=entryNode("tr");row.append(entryNode("td",sceneCatalog.definitions[kind].label),entryNode("td","8 / 8"),entryNode("td",entry.views.se.camera_profile_id ? "统一投影重制（监管台共用桌型）" : entry.views.se.coverage==="drawn"?"历史方向图":"声明旋转对称复用"));document.getElementById("coverage").append(row);}
refreshSceneInspector();
