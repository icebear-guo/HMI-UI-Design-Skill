# MCGS适配导出选择与交接

1.06在有效导出选择之后继续做[接口兼容检查](mcgs-interface-compatibility.md)。默认不兼容即停止正式输出；用户明确需要待适配符号要求时使用--allow-symbolic-unsupported，仅生成mcgs-plan.symbolic.json并保留partial。不得改设计或配置来换pass；两分支均记录execution-compatibility.json。

本文未另说明的逐阶段确认条件均适用于默认评审模式。用户明确委托跳过指定评审时，执行下述delegated分支；不得伪记confirmed。

## 流程末尾询问

流程1参数、流程2代表页、流程3全套交互HTML已获当前版本确认后，展示已完成成果，再问：

> 是否同时导出 MCGS 适配的资产文件和完整落地规格？

选择“是”记录为export，选择“否”记录为decline。无答复不是同意。用户此前对当前已呈现版本明确要求该适配包时可引用原答复，不重复索要相同授权。明确导出要求也不替代尚未完成的设计确认。

普通UI交付不受该选择阻塞；未选择或拒绝时不制作MCGS专用资产/字段包。项目改版影响已审成果后，原导出选择失效，重新展示当前成果再确认。

## 记录和检查

project-workflow.json中mcgs_export默认null。真实答复后填写decision(export/decline)、design_revision(流程3 revision)、reviewed_digest(当前流程3摘要)、customer_message、message_ref、confirmed_at(含时区)。不得编造用户确认；检查工具只能验证字段和成果身份，不能认证用户原话。

```powershell
python scripts/check_project_workflow.py --record 项目/project-workflow.json --for mcgs_export
python scripts/export_handoff.py --spec 项目/handoff-spec.json --assets 项目/assets --workflow 项目/project-workflow.json --out 项目/mcgs_specs
```

只有设计三项确认和当前版本导出选择均有效时返回ready。缺选择、拒绝、版本/摘要过期都不会放行MCGS导出，但--for delivery仍按普通设计确认检查。

handoff的source_sha256必须对应流程3已审核快照内的实际源文件；source_inventory_file必须是该快照登记的JSON文件，其数组与source_inventory完全一致。组件源、库存和导出资产不得来自不同版本。

## 设计前先了解目标能力

目标为MCGS且用户已提供模板时，在流程1/流程2前先让工程侧只读盘点版本、画布、页面、变量、图库、合法控件供体及已有验证证据。UI据此选择可落地组件；默认仅使用指定模板内供体；缺某种控件时保留设计资产并列出待落项，不直接压平页面或用假灯代替图片。只有用户另行明确允许跨模板时才查外部供体。无模板时将依赖目标能力的项目标为待核实，不把HTML效果当作原厂能力。此盘点不写MCP、不提前渲染PNG，也不增加一轮客户设计确认。

## 一次生成的内容

独立1:1 PNG来自同一组件源直接渲染；标签、灯、按钮、装饰、机械设备和管线分层不变。规格导出器一次生成handoff-spec.json、content-spec.csv、text-spec.csv、asset-spec.csv、mcgs-plan.json和validation.json，连同资产和可编辑组件源交给MCGS skill。

mcgs-layout-plan/1.1是已转换的**符号化落地字段**：实际控件类型、规范化对象名、LTRB框、LOGFONT负像素字号、颜色语义与COLORREF、逐态图库名/文字、灯文字子项、数字样式、跳转窗口、公共窗口关系及工厂需求。它不含猜测的MDB字节偏移、运行ID或PLC地址。resolved_id=null明确交由工程模板解析，不属于漏填设计字段。

## 后续由MCGS skill执行

1. 冻结目标工程，解析版本/模板/图库/变量与供体，逐组件解析实际ID和可用工厂；缺工厂只列具体待适配项，不合并背景。
2. 给出预检和完整组件对账，校验文字框/字体、按钮两态图文、数值样式与单位、导航目标和业务页公共引用。
3. 另存新MCP并全表回读；显示、组态检查、编译、模拟/真机验证分开报告。

UI skill不写MCP。当前字段计划不是运行工程，也不包含推测的启停/联锁/报警逻辑。未接收并解析目标工程，不宣称符号化计划已能直接编译运行。
