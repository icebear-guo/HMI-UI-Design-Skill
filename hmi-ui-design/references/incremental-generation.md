# 1.06 增量生产与停止条件

本文的阶段/生产PNG约束只管理正式通用素材交付；HTML预览复制可以随时为本次所选控件即时渲染必要图片，不等待流程3，不批量导出未选中的素材。

## 先确定影响，再生产

1. 列实际改动及依赖：组件源、共享CSS/字体、母版、文字/数据、状态、尺寸和所属页面。只有描述/字段改变、PNG内容未变时不重画图片。
2. 草稿源调用 `sync_component_sources.py`，相同UTF-8内容跳过写入；改动项局部替换。旧计划中消失的文件列obsolete并保留，不自动删除。完整项目传入workflow，工具拒绝写入已确认/委托的评审快照。
3. 正式导出写新批次；缓存根据捕获定义、环境和该源文档实际加载的依赖内容判断命中。单组件源改变不使其他无依赖组件失效；共享CSS改变会使依赖它的组件重跑，报告具体依赖。
4. 失败前成功的独立缓存条目可在新批次复用。新批次仍核对PNG哈希/尺寸和全部清单覆盖，失败批次不能直接当成功包。

```powershell
python scripts/sync_component_sources.py --plan project/source-plan.json --draft-root project/draft --workflow project/workflow.json
```

输入schema为`hmi-source-files/1.0`，files每项为`{file:"button.html",content:"实际完整源文本",component_ids:["button_start"],page_ids:["overview"]}`。file是draft-root下相对POSIX路径，禁止越界或链接。组件/page ID仅帮助说明影响；最终缓存命中仍由真实依赖决定。不把工具指向已确认目录。

## 静态导出源的页面复用与缓存

旧render manifest仍可直接使用，继续每项重新加载。只有专用、可重复的静态导出源才增加：

```json
"optimization": {
  "static": true,
  "source_root": "source",
  "cache_dir": "render-cache",
  "backend_key": "当前已核实环境与驱动配置的稳定标识"
}
```

source_root是manifest目录内的专用子目录；源、输出和缓存互不包含。该目录包含所有本地HTML/CSS/JS/SVG/图片/字体依赖，禁止链接和外部资源。静态声明要求无时间、随机数、存储、URL路径依赖、持续动画、网络或交互状态变更；不把动态原型直接声明为静态。渲染器冻结本批源副本、阻止快照外资源，按源URL/视口/fragment分组并复用已就绪文档。持续动画和音视频会报错。

缓存绑定捕获定义、浏览器文件/版本目录、系统与本机、字体元数据、软件模式及backend_key；可用`backend_report`指向环境探测JSON，其cache_identity同样进入键。记录原始捕获的真实依赖文件及SHA256。驱动/字体/环境改变时刷新环境报告或backend_key，必要时`--no-cache`重测。文件缓存不证明当前GPU实际生效。

```powershell
node scripts/render_components.mjs project/render-manifest.json project/render/new-batch
node scripts/render_components.mjs project/render-manifest.json project/render/verification-batch --no-cache
```

每个缓存命中均重新检查依赖内容、PNG哈希与尺寸。页面预览、collect_hmi和capture:false探测始终实际执行，不复用旧DOM证据。报告区分cache_hit、原次测量、当前测量和真实renderer；全缓存命中不启动浏览器且renderer为null。最终包只收当前清单选择的PNG，不打入cache、checkpoints或source-snapshot。

同一HTML内其他组件变化时，该HTML的捕获会保守失效；希望精确到单组件时，为其提供独立导出HTML并共享必要CSS/母版。工具不声称已理解任意自写生成器的业务依赖，也不会自动改造正在运行的全量入口。

## 从一份几何数据派生渲染清单

`prepare_render_manifest.py --project project/render-project.json --out project/render-r2.json`读取delivery输入中的页面/资产尺寸与ID，结合仅含HTML/selector的capture map，输出渲染清单及相应的`.delivery.json`。输出和项目配置位于同一目录，均不得已存在；报告给出新的PNG目录。这样无需重复填写图片尺寸/文件路径。

项目schema为`hmi-render-project/1.0`，字段：browser、delivery_manifest（相对JSON）、captures={assets:{资产ID:{html,selector}},pages:{页面ID:{html,selector,brand_selector}}}，可选optimization、software_rendering。映射须完整且无多余ID。页预览需要实际公司标签。fonts、inventory等原delivery相对引用继续保留，不能借派生清单绕过原校验。

## 默认检查与停止

- 人工判断布局/配色/精致程度；AI默认检查尺寸、边界、文本容纳、有效alpha、缺图缺态、引用及字段，并提供遮挡线索。机械检查不冒充审美通过。
- 改稿须对应用户修改意见或明确机械错误ID。集中修复后验证受影响项；同一根因连续两次未解决则报告剩余项与证据，停止自动改稿。新证据或用户新要求可重新开始相关工作。
- 不反复截图追求更好看；不把全流程、delegated或工具partial当作无限审美授权。有效的人工作品确认不因AI主观偏好失效。
- 区分机械fail、能力blocked、人工awaiting_review及原厂not_run；能力未变时不重跑同一工具期待pass。保留最终完整清单对账，不重复渲染全部图片。
- render-report.metrics分别记录环境/源处理、缓存查询、浏览器启动、捕获、页面加载次数及复用/渲染数量；checkpoints.jsonl保留逐组件完成证据。对话等待另计。

