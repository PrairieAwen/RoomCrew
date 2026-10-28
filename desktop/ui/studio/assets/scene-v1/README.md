# 场景运行目录 scene-v1

本目录保存当前 scene-assets v1 运行合同；版本号表示合同，不表示图片都来自第一批美术。最新八类设备及四角色配套工作/起坐图来自 ../scene-v2/，范围、来源与未完成项见其 README 及 ADR-0020。

## 当前保留内容

- catalog.json 为登记事实，catalog.js 为相同 JSON 的浏览器只读包装；14 类设备共 112 个方向槽，对称复用明确标注，不当作独立原绘。
- index.html / inspector.js 提供设备、配套人物、起坐关键帧与接触点预览。
- 四张 seated-*.png 保留旧八向坐姿参考；cabinet.png、coffee.png、fridge.png 仍被当前目录引用。
- workstation-v3.png 只保留其仍在使用的独立键盘附件；window-garden-v2.png 仍是窗景来源。
- generation*.json 与 prompts.json 保留来源追溯。被新批次替代且无运行引用的旧图已删除；历史文件可从 Git 提交 50e3718 查阅，不再打包备用版本。

## 登记与边界

在项目根运行 `.venv/Scripts/python.exe packaging/register_scene_assets.py` 重新生成目录。脚本直接读取当前几何图集和仍需兼容的来源，只分析透明轮廓与元数据，不修改图片像素。修改登记后应验证方向、接触、原生场景及总览加载。

制作与验收遵循 doc/assets/asset-production-standard/README.md。内置显示最多五页，用户仍按原两页合同导入；不能修改用户源清单或帧号。配套椅限匹配角色及座高 22 的标准预设，关键帧不代表全动作八向循环。

用户图集的 hip / soles 使用虚拟帧坐标；内部补帧使用登记后的世界局部接触点，两者不能混用。外部家具导入、完整手脚 IK、骨骼编辑器及家具拖拽尚未实现；当前素材仅为兼容预览。
