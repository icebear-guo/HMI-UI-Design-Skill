# 1.05 组件渲染与内容验收

技能1.06新增[静态文档复用与按依赖缓存](incremental-generation.md)。旧manifest继续兼容；只有满足静态契约的专用源才能启用优化。缓存命中重新核对PNG及依赖，DOM探测和页面预览仍实际执行。视觉效果人工确认；机械检查或像素差异不授权AI反复美术改稿。

文件存在、PNG 尺寸正确、图库引用齐全分别只证明各自事实。生产导出还要检查有效图像内容及使用最终 PNG 的重组页面。

## 批量渲染入口

`node scripts/render_components.mjs 项目/render-manifest.json 项目/新的资产目录`

需要 Node 22+（内置 WebSocket）与可用 Chrome/Chromium。manifest 格式：

```json
{
  "schema_version": "component-render/1.0",
  "browser": "浏览器可执行文件绝对路径",
  "software_rendering": false,
  "components": [
    {"id":"panel_s0","html":"components/panel.html","selector":"#component","width":214,"height":120,"file":"panel_s0.png"}
  ]
}
```

组件 HTML 位于清单目录内，来自同一已审组件源；selector 指向无缩放的精确画布，阴影留白纳入画布。工具复用一个浏览器进程，显式设置 CSS viewport 与 DPR=1，读取 innerWidth/innerHeight 和元素实际框；等待字体、图片和两次绘制后按元素 clip 导出。不得用浏览器外窗口的 `--window-size` 充当网页 viewport；小尺寸外窗口可能只剩极小网页区域。

输出目录必须不存在，按 [追加式生成](generation-lifecycle.md) 分配；失败保留已写图片和render-report.json，不能使用失败批次冒称完整资产。记录实际 renderer 和逐图耗时；WebGL 后端信息不能证明所有 Canvas/SVG 操作均走 GPU。默认不禁 GPU，必要软件回退由 manifest 明示。关闭本批浏览器会话，私有配置留在系统临时目录并在报告记录，不递归删除、不进入交付。

## PNG 内容预期

每资产 `content_expectation` 来自源图元几何，不能在看到残图后按残图反填。例如面板可声明：

```json
{"mode":"visible","required_bbox_px":[4,3,210,111],"tolerance_px":2,"min_visible_fraction":0.5}
```

bbox 使用组件画布的 LTRB；表示必须至少覆盖的可见内容范围，不是控件位置。`asset_quality.py` 检查 alpha 非空、内容 bbox、可选可见面积下限；export_handoff 自动调用。全透明仅允许真正设计为空态的 `{"mode":"empty_state","reason":"明确设计原因"}`，不能把丢失设备改成 empty_state。细管线、空心框、阴影和实体面板各自给合理预期，不使用统一面积阈值。bbox/面积检查仍不能发现所有内部缺笔，不能替代重组对照。

## 最终页面重组

用最终导出 PNG 加可编辑文字/动态初值，按实际 z、页面/公共页关系重组；对照同版本源 HTML 渲染。不得重新调用源 SVG 代替待验 PNG。记录差异范围、透明边缘和可接受抗锯齿容差，逐页检查设备、面板、图标、管线、灯及公司署名。状态图做各态组件检查；页面初态通过不证明所有状态/交互通过。

当前 export_handoff 返回 `status=partial`，checks.machine_spec/asset_content 可为 pass，rendered_composition/source_visual_inventory/native_display 等未执行项保留 not_checked/not_run。只有另外完成真实重组和视觉库存验证才能报告相应通过；不得手工改总状态来代替检查。

最小代表页先覆盖新工厂和典型尺寸，验证后再扩多页；不要求固定行业、六页或固定设备。


页面预览捕获项设置role="page_preview"并给brand_selector；渲染器读取实际DOM公司标签，检查文字、祖先可见样式及屏内矩形。manifest.company_name可给用户指定名称，缺省为“工控北极熊（抖音）”。缺节点、隐藏、错误文字或越出可视区会失败。这是DOM可见性检查，仍不证明没有被其他图层遮挡；资产导出项不包含此公司文字，署名继续由原生独立标签承载。
