# 最终资产范围与逐元素覆盖

本规则用于已确认UI的最终工程交付。C1参数、C2样例HTML、C3规定数量全套交互HTML全部确认前，只在HTML中设计、盘点和列出预计资产，不提前渲染PNG或切图。资产豁免可随C3的交付范围表一并提交客户确认，不另造默认通过的审批。

## 默认导出范围

从C3确认的每页HTML开始，逐项登记全部可见图形、组件子层和必要状态。以下图形默认提供可直接取用的独立透明PNG；可编辑矢量源能提供时另附。

| 类别 | 必须盘点的内容 |
|---|---|
| 图标 | 用户人形、导航、警告、通信/链接、工具、操作提示、装饰符号等 |
| 指示状态 | PLC小灯、IO LED、设备状态灯，以及实际定义的ON/OFF、运行/停止、故障/离线等状态 |
| 组件皮肤 | 按钮底板、按钮图标、选择块、输入外框、弹窗/提示皮肤、面板及自定义表盘/轨道等静态部分 |
| 页面图形 | 背景、边框、设备图、插画、装饰、当前项目允许提供的标识等 |

不因元素面积小、只装饰、非按钮、用CSS绘制、由内联SVG绘制或可替换为平台图标就自行省略。图标与底板分别映射，不能只导出整个按钮后宣称独立图标已提供；一个顶部栏“native”条目不能覆盖其全部人形、通信和警告子图标。

文字、实时数值、趋势曲线与原生仪表/棒图的动态绘制部分保留可编辑、可绑定的实现规格，不要求把每个字或采样点切成图片。原生控件内若存在独立自定义图标、灯、静态表盘或装饰，仍作为graphic子项盘点。项目没有使用的类别无需凑素材。

## 每项必须有明确去向

| delivery_mode | 需要提供 | 客户确认条件 |
|---|---|---|
| export | 每个required_state的独立asset引用、角色、画布、锚点及状态语义 | 按已确认UI正常导出 |
| native | 目标控件、绘制/字体/颜色/尺寸等参数、绑定与每个状态的实现方式 | 文字和动态内容属于正常原生分工；图形不导出属于例外，须客户逐项确认 |
| merged | 静态子元素对应的同页父背景/面板资产、位置关系与原因 | 须客户逐项确认；指示灯和多状态图形禁止合进静态背景 |

图形采用原生、仅矢量或静态合并等不提供独立PNG的例外，要列明元素ID、所在页面、当前UI版本、实现规格/源文件或父资产、原因及客户真实回复。不能仅写“native”“工程端自行替换”或“无需导出”。当前助手的打包器只复制PNG与许可字体；独立SVG等工程源需要另外随包附带并核对，不把HTML内联代码自动算成已经交付独立源文件。

共享资源可只导出一份，但每页、每个组件实例都需要映射。复用不免除实例覆盖；状态语义不同也不能仅根据颜色合并资产。按钮底板的s0/s1与指示灯设备状态分别定义，不能把disabled当作pressed，也不能把所有图形都套s0/s1。

按钮底板继续遵守用户要求的独立s0/s1交付，不适用本助手的native/merged图形豁免；每个按钮实例映射一套同画布底板。1.2通过各实例inventory中的asset_refs复用同一套底板，不强求共享资源的component_id与每个实例layer_id相同。

## 构建清单1.2

使用 [元素盘点模板](../assets/element-inventory.template.json)，在 [最终构建清单](../assets/delivery-manifest.template.json) 中用 `element_inventory` 内嵌该对象，或填写相对JSON文件路径。模板是合成示例，按实际C3页面替换，不代表客户项目已确认。

资产新增 `asset_role`。同一 `component_id + asset_role` 内的状态画布保持一致；底板和图标可以使用不同尺寸，也可具有相同state名称。最终specs/design.json保存解析后的完整盘点。

盘点根字段：`schema_version="1.0"`、`ui_revision`、按页面顺序的 `reviewed_page_ids`、非空 `elements`。ui_revision对应实际C3确认版本。

每个element包含：

- `id,page_id,layer_id`：本页元素ID及父图层；同页元素ID唯一，父图层必须存在。组件可拆成底板、图标、文字、状态灯等多个element。
- `category`：graphic、editable_text或dynamic_content；图形不能伪装成文字或数据豁免。
- `asset_role`：图形为background/panel/control_plate/icon/indicator/device_illustration/decoration/frame/track/needle；文字/动态内容分别用editable_text/dynamic_content。
- `rect_px`：设计画布坐标 `[x,y,w,h]`，独立PNG画布宽高对应本元素宽高；透明留白计入画布。
- `required_states`：实际必需的状态列表；静态图形也明确default。
- `delivery_mode`：export、native或merged，不留待定项。

export额外提供 `asset_refs=[{"state":"default","asset_id":"user-icon-default"}]`。引用必须存在，角色、状态和尺寸匹配；每个必需状态都有映射。不同指示状态的实际解码像素需可区分，不能只改文件名。

native提供 `native_spec={target_control,parameters,state_map}`。parameters为可重现的非空参数对象，state_map覆盖全部required_states。图形还需 `customer_waiver={status:"confirmed",ui_revision,reason,customer_message,message_ref,confirmed_at}`；时间带时区，版本必须匹配，禁止编造客户回复。

merged提供 `merged_into`指向同页已导出的静态background/panel元素，并提供同格式customer_waiver。子元素必须位于父资产矩形内；不能跨页、合并到缺失父项或把动态灯态藏进背景。

## 最终检查

构建与验收调用 `scripts/asset_coverage.py` 的共享检查：逐页记录、图层处置、独立资产引用、角色、状态、尺寸、客户豁免、静态合并父项与未映射文件。清单缺项、缺图、缺状态或无效豁免均失败。旧1.0/1.1包仅保留兼容检查，标为missing_legacy_inventory，不能宣称已满足当前完整图形范围。

代码只能核对已登记图层/元素，不能凭空推断未录入清单的人形或小灯。最终还须把C3已确认HTML与盘点、资产联系表逐页对照，记录漏项、修正和原生豁免。`complete_registered_inventory`只表示登记内容对账通过，不代表视觉盘点、客户确认、浏览器或目标工程均已验证。
