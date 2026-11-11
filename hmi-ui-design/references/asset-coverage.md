# 逐元素覆盖与交付对账

背景、布局、灯、文字、按钮、装饰色块、装饰图标、设备及其独立子层在设计源中分别建模。流程3确认前冻结源组件清单，导出后按清单对账；不要从已经导出的背景文件反推一份更短的清单。

## 当前有效的两种实现方式

| delivery_mode | 用途 | 必须信息 |
|---|---|---|
| export | 独立图形直接组件渲染PNG | 页/元素/源节点ID、角色、矩形、逐态asset_refs、同画布与锚点 |
| native | 可编辑文字、动态数据，或经用户确认并已验证的原生图形 | target_control、完整parameters、逐态state_map；图形还需真实用户确认 |

完整交付不支持merged。背景只承载自身底色/纹理，不承载独立导航、面板、分隔线、图标、设备或灯。组合组件保留子树，不能只交组合大图。合法共享母版允许复用文件，但每个实例都需独立映射、位置和工程对象。

模板没有某控件、颜色偏移未标定、像素一致、控件数量、静态或可运行用途都不能自行豁免。缺适配能力时保留独立资产/规格，列出待适配ID；禁止假灯绑定占位变量、缩减原始清单或把未交独立图形宣布为完整交付。

## element_inventory 格式

根字段schema_version="1.0"、ui_revision、reviewed_page_ids、elements。每元素含id/page_id/layer_id/category/asset_role/rect_px/required_states/delivery_mode。category为graphic/editable_text/dynamic_content；图形角色为background/panel/control_plate/icon/indicator/device_illustration/decoration/frame/track/needle。

export逐态列asset_refs=[{state,asset_id}]，图片尺寸对应元素矩形。native列native_spec={target_control,parameters,state_map}；图形原生例外同时有customer_waiver={status:"confirmed",ui_revision,reason,customer_message,message_ref,confirmed_at}，仅能记录真实用户决定。文字/动态数据为正常原生分工，不需图形豁免。schema1.2包必须给出完整inventory；旧包兼容检查不能代表当前完整覆盖通过。

每个按钮实例须有独立s0/s1底板映射，按钮文字保留可编辑子层并归该按钮；图标与状态点分别映射，不靠按钮图掩盖缺项。灯内部文字与灯旁说明按text_owner分别处理。

## 检查

文字最终框、导航原生按钮归属与公共窗口机制见 [原生复制规则](mcgs-clipboard.md)。设备图鉴另按 [equipment-atlas.md](equipment-atlas.md) 检查，不能省略或只用方框占位。

