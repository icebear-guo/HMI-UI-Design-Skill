# 同源机器交付清单 · 1.05

技能1.06接口修订见[兼容说明](mcgs-interface-compatibility.md)。数值按factory/native_type识别；按钮vertical_align及完整局部框保留到计划。代表页可无PNG预检。默认正式导出阻断不兼容配置；显式待适配分支只写mcgs-plan.symbolic.json和差异报告，不写常规mcgs-plan.json。共享schema版本不变。

输入 `handoff-spec.json` 是已确认组件源的规格，不从截图 OCR 或后期人工估计生成。示例见 `assets/handoff-spec.template.json`。导出命令：

```powershell
python scripts/export_handoff.py --spec 项目/handoff-spec.json --assets 项目/assets --workflow 项目/project-workflow.json --out 项目/specs_export
```

用户确认MCGS导出后，一次输出 `handoff-spec.json`、`content-spec.csv`、`text-spec.csv`、`asset-spec.csv`、`mcgs-plan.json`、`validation.json`。输出到新目录；不覆盖已交付版本。执行前按 [mcgs-export-workflow.md](mcgs-export-workflow.md) 记录最终导出选择；源和组件库存必须来自已审快照。工具只校验/导出规格，不生产 PNG；PNG 来自组件直接渲染。

## 页面与组件

根字段：schema_version="1.05"、design_revision、source_sha256、target、branding、pages、assets、source_inventory、source_inventory_sha256。source_inventory在流程3确认时冻结，每项为page_id/component_id/role；其SHA是该数组UTF-8 JSON（ensure_ascii=false,sort_keys=true,separators=(逗号,冒号)）的SHA256。保存于评审快照，不能在导出时删减以迁就少量背景文件。页面包含 id/name/canvas_px/common_page_id/controls。每个 control 的 id 在页内唯一，列出 kind、role、rect_px（页坐标 x/y/w/h）、parent_id、z、states、texts、binding、target_page_id。项目不适用项以 null 或空数组明确表达。

角色区分 background、layout、indicator、text、button、decoration_block、decoration_icon、equipment、pipe、arrow 等，不以整页/整条公共栏遮蔽动态子层。

每个 state 含 id、asset_id（文字/数值/逻辑组可为空；MCGS按钮、指示灯和状态切换逐态必填）和 semantic；s0/s1 不自带业务语义。每资产含 id/file/component_id/page_id/state/design_size_px/export_method="component_render"/source_component_id/text_baked=false。source_component_id 指向能独立渲染的同源节点；源组件树及设备组合关系必须保留。既有位图迁移另行记录，不假装由新组件源导出。

## 每段文字

每项 texts 包含 id、text、state、text_owner、rect_px、font_family、font_size_px、font_weight、color、align、line_height_px。state=null 表示各态共用；其他值须在父控件 states 中存在。

- component：用于按钮单段caption或明确的灯内单段文字，rect_px 为控件局部坐标；输出同时计算绝对坐标。多段信息/IO卡片默认先拆独立控件，不能直接把三段标成component后内嵌。确需原生多段时提供 `native_multi_text_layout_verified={software_version,result,evidence}`，result须为passed_in_native_editor且有真实版本/证据；字段校验只验证声明，不代替原厂验收。
- external：该控件必须为独立 text/label 类型，rect_px 使用页面坐标；指定 parent_id 仅表示设计结构，不意味着写进父控件的两态。

文本中的换行和完整字符保留，CSV 正常引号转义，不把字面量反斜杠 n 当换行。text-spec.csv 每行一段文字，包含页/控件/文字 ID、归属、状态、局部/绝对坐标、字号/尺寸/字重/颜色/对齐/行距，供其他 skill 直接使用。

content-spec.csv 每行一个控件，保留类型、坐标、尺寸、层级、资产状态映射、文字归属及绑定；多段/多态文字通过 text-spec.csv 关联，不能截成单一“文字”列丢失状态。asset-spec.csv 每行一资产，记录实际像素、SHA、源节点、状态、导出方式。JSON 保留完整关系，CSV 是便于工具读取的展开表。

binding 必填name/access(read_only或read_write)/signal_role(command、feedback、measurement、setpoint、local_demo)，并记录语义、数据类型、单位、小数位、范围、初值、地址核实状态；没有 PLC 资料则地址 null，不能虚构。同一实际信号在不同控件上复用时，当前接口必须显式填写相同binding.name；不同设备的不同信号应使用不同name/语义，不能只因同叫“运行”就合并。默认按控件生成的名称不能用来证明信号共享。读数是否可编辑、命令按下/松开行为、反馈来源必须在组件源的interaction及交接说明中明确；当前符号化计划主要覆盖布局，未消费的行为逐项列为待落项，不宣称完整逻辑已编程。图层的设计 ID 与最终 MCGS 对象名映射显式记录，不能只靠页内行序猜。


## 导航、共享窗口与数值样式

页面可声明page_kind=common/business；业务页的common_page_id指向公共页，公共页不能自引用或循环。目标为MCGS时，role=navigation_button/global_status/global_header/global_alarm的共享组件仅出现在被业务页引用的公共页。每个导航button设置target_page_id，texts包含text_owner=component的非空caption（state=null共用，或s0/s1分别给出）；独立外部标签不满足导航caption要求。

mcgs_object_name可显式映射工程对象名；缺省由编译器按组件ID加稳定哈希生成，避免截断/字符替换重名。数值控件必须提供font（family/size_px/weight/color）、appearance（fill_enabled/border_enabled/image_enabled）及numeric_layout={horizontal:left/center/right,vertical:top/center/bottom,padding_px:[左,上,右,下]}，单位内外归属明确；这些字段必须进入content-spec.csv，不能使用模板默认样式兜底。

所有文字矩形都是最终适配框，源字号不能替代尺寸。组件局部矩形与页面绝对矩形同时给出；实际字形测量加留白后不得超过框，工程端应按相同字体、字号和最终框回读验收。改动影响布局时从同源组件调整，不在落工程时盲目扩框挤压邻居。


source_inventory_file指向流程3评审快照登记的库存JSON；它不是导出目录的随意文件。按钮各态必须有实际独立图片asset_id；导航caption必须同时属于该按钮，不能以外部label替代。mcgs-plan中的native_type、bounds、font.lfHeight、states、binding、target_window、common_windows由完整设计规格编译，ID/供体/MDB序列化交工程skill解析。


共享母版必须显式声明：控件asset_master_id与资产master_id/source_component_id一致，逐实例保留控件ID、位置与状态。不可仅因文件长得像就跨组件借图。数值单位若为external，binding.unit_component_id必须指向实际独立标签；internal则由数值控件单位字段呈现，不再重复建单位标签。


## 公司、内容预期与行为字段

branding={company_name:null或用户指定公司名,text_refs:[{page_id,component_id,text_id}]}。引用必须指向实际独立label的external、state=null文字，文字完整等于指定公司名或默认“工控北极熊（抖音）”。标题不能替代，PNG不得烘焙署名。检查存在/尺寸不证明图层未遮挡，逐页源HTML和最终资产重组另验。

每资产增加content_expectation，格式/实测视口工具见 [export-validation.md](export-validation.md)。它必须来自组件源图元预期，不从坏PNG反填。

按钮、可写开关和数值输入必须给interaction。导航为{type:"navigate",target_page_id:实际页ID}，与控件target_page_id一致。其他type为momentary、toggle_command、set_value、value_edit、copy_values、acknowledge、custom；scope=local_demo/plc_unverified。常规动作给command_binding，可选不同的feedback_binding；momentary再给press_value/release_value/cancel_value，取消值与松开值相同。set_value给value；copy_values给copies=[{from,to}]；custom给engineering_spec_ref和required_effect。这是交接声明，不是原生逻辑已经实现。

behavior引用的变量须出现在控件binding或根variable_definitions={变量名:完整binding定义}。同名变量的类型、范围、初值、单位等一致；command必须可写，feedback/measurement不可被UI写，copy目标可写且类型匹配。compile_plan保留variable_definitions/interaction/numeric_layout，不再隐藏在会被过滤的私有字段中。未支持属性由MCGS返回差异，不删字段或改自页跳转兜底。

旧schema1.04需从原设计源迁移；新增字段经实际设计核对后生成1.05，不能只改版本号。设备子层/母版实例继续保留完整库存；源视觉覆盖未检查时保持not_checked。导出报告的partial明确限定已通过的规格/资产检查，不宣称已通过原厂显示或程序运行。


设备/零件工艺项目声明equipment_required=true、equipment_catalog_file=已审快照中的相对JSON。使用equipment-catalog/1.1先流程关系图后逐项精致图鉴，流程节点与母版/实例一一覆盖；export_handoff检查该catalog与当前design_revision及已审文件清单。流程图和图鉴源文件都纳入快照，不只登记JSON。纯IO局部样例无需该分支。


## 同一工程能力配置贯穿切图与写入

自动MCGS导出使用工程侧template-preflight.json中的execution_profile（或MCGS提供的原始配置文件）；命令行通过export_handoff.py --execution-profile指定。配置的profile_id和实际文件SHA保留在handoff-spec.target_execution_profile、mcgs-plan.execution_profile以及正式CSV。重编译计划时继续校验同一配置，不丢失版本身份。

上文schema可表达多种排版/动作，能表达不等于每种组合都已有自动写入器。实际自动导出要匹配所选工程配置；没有配置时仅交付symbolic_plan_only_not_execution_ready，不声称字段都可自动落工程。背景/底板/数字/输出单位的对象关系在设计阶段明确，不能临写时把内部单位改外置或把左对齐改居中。
