# 1.06 MCGS接口修订

设计schema继续1.05，符号计划继续mcgs-layout-plan/1.1，工程execution_profile继续1.0。未单方面升级共享配置，也未修改工程安装目录或MCP。

## 配置与能力边界

工程1.0 profile未完整声明scope、输入类型和按钮文字框限制。`assets/legacy-execution-guard.json`记录从已审核工程代码读取的兼容限制，绑定原profile ID、原文件SHA256和规范化内容SHA256，并记录工程代码指纹。它是UI侧只读防护，不是新MCGS能力配置，也不证明实际模板有供体。

仅对精确匹配的已审核配置应用这些限制。未知schema、身份、哈希或内容改变均阻断；须与工程侧共同核实后更新，不拿旧限制猜新能力。UI运行无需导入工程目录的Python模块。未来升级共享profile须同步双方读取器及总控调用者。

| 接口 | 当前已审核路径 | 差异处理 |
|---|---|---|
| 瞬时按钮 | momentary＋local_demo，可写boolean/number变量，适配值为有限数值；布尔变量用数值0/1 | PLC范围、字符串变量、JSON布尔值等列具体字段，不静默改成演示 |
| 数值输出 | existing_numeric_output_or_verified_factory＋0x5008，始终检查绑定、排版、外观、字体和单位 | role改为measurement不改变数值路线；未标定right对齐阻断 |
| 数值输入 | native_input_with_format＋0x5025，当前声明类型number；工程仍须验证真实ObjData.kind=2 | boolean输入提前拒绝，不连带拒绝布尔显示、反馈或灯 |
| 按钮文字 | s0/s1完整内部caption；水平left/center、垂直top/center；局部框等于整按钮 | right/bottom、自由子框、缺垂直对齐或双态样式不一致返回差异，不外置caption兜底 |

role只表达业务用途，类型由factory/native_type合法配对识别。numeric_input的PLC声明不套用button_local_momentary的local_demo限制；数值输入地址、实际变量类型与设备执行仍待工程验证，额外动作脚本须专用适配。

文本可选vertical_align=top/center/bottom，保留为计划的vertical_alignment。普通UI仍可表达这些排版；选中当前MCGS按钮路径时必须明确填写，不猜默认值。button_text_styles保留每态caption/font/color/horizontal/vertical，并与内部文字交叉检查。

瞬时按下/松开源码、取消复位、丢焦复位和设备执行分别记录，不用源码回环代替原厂行为验证。automatic_execution_ready保持false，模板及原厂显示/行为另记not_run。

## 代表页能力检查

```powershell
python scripts/execution_profile.py --spec project/handoff-design.json --profile supplied/execution-profile.json
```

只在内存中检查设计能力，不要求生产PNG，不填假资产哈希，不输出工程计划，也不认证客户确认。JSON差异含page_id、component_id、field、requested、supported、blocking_stage和resolution。退出码0仅表示编码约束匹配，2为不支持/配置阻断，1为输入错误。

已有正式计划用--plan代替--spec。检查参数不能静默替换计划内profile身份。

## 正式导出

默认export_handoff严格检查，不兼容时在创建输出目录前失败；CLI返回execution_compatibility，保留原设计。

明确要保留待适配规格时添加--allow-symbolic-unsupported。仍检查阶段/选择、规格、真实PNG和文字，输出partial及组件差异；待适配计划名为mcgs-plan.symbolic.json，不生成常规mcgs-plan.json。它不能放行工程自动执行。兼容分支继续使用常规文件名，但仍须真实模板解析及原厂验证。

两分支均附execution-compatibility.json，由本技能检查器实际生成。原设计target_execution_profile与CLI选择不一致时先阻断重检。已有资产文件/像素哈希改变时不得静默更新旧值；设计revision和配置身份持续核对。

## 工程侧依赖

已审核工程preflight仍有role分流缺陷，UI修正不等于工程读取器同步。工程侧须按factory/native_type分流、尊重不支持状态，并解析真实供体。审查中数据库、图库、改名、快照和报告问题仍由工程任务处理。

当前没有通用计划→MCP执行器。通用配置匹配不等于模板或自动执行就绪。联合验收需同一真实模板完成正式导出→供体解析→内存适配→候选工程→独立回读；原厂显示/检查/编译/运行分别留证。本轮UI测试使用合成规格、实际PNG/字体和真实导出路径，不执行MCP写入或原厂运行。
