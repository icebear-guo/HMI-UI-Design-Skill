# HMI UI Design Skill｜工业人机界面设计技能

当前技能版本：**1.0.3**，以 [SKILL.md](hmi-ui-design/SKILL.md) 的 `metadata.version` 为准。技能版本与交付清单的格式版本分别维护。

面向工业触摸屏、设备操作面板与监控画面的 AI 设计技能，覆盖需求引导、配色与布局打样、分层组件、按钮双态切片、可交互 HTML 原型和分范围验收。

完整 UI 项目按“初始参数确认 → 样例 HTML 确认 → 全套交互 HTML 确认 → 正式切图与交付”推进。技能由通用规范、可更新的方案库、模板和本地构建工具组成，可配合支持 `SKILL.md` 的 AI 工具使用。

## 使用流程

**正式结果输出前，评审全部以HTML为主。C1/C2/C3未全部确认，不提前渲染PNG，不先切图，也不将静态图片嵌入HTML冒充交互评审稿。** 页面、组件、按钮双态先用HTML/CSS/内联SVG呈现；已存在的客户位图可只读引用。

项目开始时先向客户展示以下清单，说明每次需要客户确认的具体成果，以及确认后才会开始的下一阶段。

| 阶段 | 提供给客户的清单与成果 | 由客户确认 | 确认后可以进行 |
|---|---|---|---|
| **C1 初始参数** | 原生分辨率宽×高、已提供的屏幕尺寸、导航位置及项目数量、色调约束、明确的页面数量和名称/ID、语言、必要交互及输出要求 | 当前版本的参数汇总与页面范围；允许提出暂定值，但须明确哪些仍待核实 | 制作代表页面 HTML 样例 |
| **C2 布局与色调样例** | 默认同一代表页的 3 个 HTML 候选，保持相同画布、内容及初始数据；允许混选布局与配色，并显示组合后的最新代表页 | 实际打开评审的最新 HTML 对应的布局、色调及调整结果 | 按选定方向制作规定数量的 UI HTML |
| **C3 全套交互 UI** | C1 约定数量的全部 UI HTML、逐页入口、页面数量核对和交互检查记录；实现适用的按钮反馈、灯/IO切换、模拟强制、真实切页、参数输入、仪表与棒图联动 | 全套页面的当前版本、数量、内容与交互；有修改则修订后重新提交 | 正式切图、生产 PNG 导出、最终交付打包 |
| **最终制作与交付** | 按已确认画面制作独立 `s0/s1` 切片、页面 PNG、标注、资源清单和 ZIP，运行相应检查 | 对照已确认版本核对交付；新增变更回到受影响阶段 | 完成本轮最终输出 |

**C1、C2、C3 三项都得到客户对当前版本的明确确认后，才进行正式切图和最终资产输出。** 样例 HTML 和全套交互 HTML 是阶段评审成果，可以先提供；不能以验证渲染管线为由提前批量切图、导出生产 PNG 或打包最终交付。

“暖灰浅色＋左侧导航”等回答只表示偏好，不等于客户已经看过并确认 HTML。即使客户已给出方向或已有设计系统，也至少提供一版当前代表页 HTML，完成 C2 确认。文件已生成、默认高亮、脚本检查通过、客户未回复，都不构成客户确认。

图库与HTML设计以客户给出的分辨率宽×高建立画布，不另问屏幕比例。初始问询已移除工程软件及版本、操作方式、现场光照；这些内容不作为必填或推进条件。客户主动提供的相关约束可直接采用。

每次确认记录客户原话或消息位置、对应文件与版本。参数、布局色调、页面数量或交互发生影响后续成果的变更时，相关确认失效；修订并再次确认后再继续。等待确认期间可完善无依赖的规格或修复阶段样例，不能自行进入下一阶段。

只要求局部修改、单项素材或规范评审时，按明确范围执行，不将这些任务冒称为完整 UI 项目交付。详细规则见 [项目流程与客户确认](hmi-ui-design/references/project-workflow.md)。

## 目录

```text
.
├─ hmi-ui-design/
│  ├─ SKILL.md                 技能入口
│  ├─ agents/                  工具界面元数据
│  ├─ references/              参数引导、设计、交互、交付与验收规则
│  ├─ assets/
│  │  ├─ style-catalog.json     配色与布局方案注册表
│  │  ├─ project-workflow.template.json  项目阶段与客户确认记录模板
│  │  ├─ themes/               独立配色方案
│  │  ├─ layouts/              独立布局方案
│  │  └─ ...                   需求、页面、打样及交付模板
│  └─ scripts/                 打样、切片、打包与检查工具
├─ examples/
│  ├─ style-proposal/          同页多布局与色调比较样例
│  └─ interactive-preview/    本地交互样例与构建输入
├─ tests/                     验证程序
└─ requirements.txt
```

仓库不包含原始资料、训练记录、私人项目文件或本机环境配置。样例采用通用内容与本地模拟数据。

## 作为技能使用

将 `hmi-ui-design/` 整个目录复制到目标工具可识别的 `skills` 目录，保留内部结构。调用时可引用 `$hmi-ui-design`，或让工具读取 [SKILL.md](hmi-ui-design/SKILL.md)。

示例请求：

> 使用 hmi-ui-design 为设备设计 1024×600 横屏界面。先展示项目流程并请我确认参数与页面数量，再提供同一总览页的布局/色调 HTML 样例。样例确认后制作约定数量的交互 UI HTML；全套确认后再切图和打包输出。

## 本地构建

需要 Python 3.12+。图像检查与切片依赖 Pillow；纯代码逻辑检查还需要可用的 Node.js。HTML 使用本地资源，无需登录、CDN 或本地服务。

在仓库根目录安装 Python 依赖并创建输出目录：

```sh
python -m pip install -r requirements.txt
mkdir exports
```

生成首次方向打样：

```sh
python hmi-ui-design/scripts/build_style_proposal.py --manifest hmi-ui-design/assets/style-proposal.template.json --out exports/style-proposal
```

完成后打开 `exports/style-proposal/index.html`。已有比较样例位于 [布局与色调HTML](examples/style-proposal/index.html)。模板内参数是演示起点，实际任务需先调整画布、代表页内容与约束。

方向稿的代码逻辑检查：

```sh
node hmi-ui-design/scripts/check_style_logic.cjs exports/style-proposal/index.html
```

使用自带合成输入验证完整交互样包的构建工具：

```sh
python hmi-ui-design/scripts/build_delivery.py --manifest examples/interactive-preview/inputs/delivery-manifest.json --out exports/hmi-ui-delivery
```

打开 `exports/hmi-ui-delivery/index.html`，在交互演示与设计标注间切换。也可打开自带的 [两页交互样例](examples/interactive-preview/delivery/index.html)。交付清单模板引用实际 PNG 文件，换成自己的设计时需同时提供对应页面与独立资产。

这些维护样例用于验证工具。实际客户项目仍须完成 C1、C2、C3，再进行正式资产构建；已有样例生成成功不代表客户项目获得确认。

### 项目阶段检查

复制 [项目确认记录模板](hmi-ui-design/assets/project-workflow.template.json) 到本次项目目录，依据真实参数、实际评审成果与客户回复填写，再在正式切图前检查：

```sh
python hmi-ui-design/scripts/check_project_workflow.py --record projects/example/project-workflow.json --for slicing
```

未填写的模板应保持受阻。阶段检查读取记录并核对其对应成果，不会生成客户批准，也不能代替客户的真实回复。具体记录格式、变更后的失效规则与检查范围见 [项目流程与客户确认](hmi-ui-design/references/project-workflow.md)。

运行文件与纯代码逻辑检查：

```sh
python hmi-ui-design/scripts/accept_delivery.py --package exports/hmi-ui-delivery --node node --scope files-and-logic
```

执行完整范围报告：

```sh
python hmi-ui-design/scripts/accept_delivery.py --package exports/hmi-ui-delivery --node node --scope complete
```

输出目录及同名 ZIP 必须不存在，工具不会覆盖旧交付。再次构建时使用新的输出名称。验收报告保存在交付目录外。

## 最终切片范围

最终交付清单现为1.2，按 [逐元素资产覆盖](hmi-ui-design/references/asset-coverage.md) 从C3已确认HTML盘点全部图形与状态。用户人形、装饰、导航/通信图标、独立小灯和IO LED、设备状态灯、皮肤和设备图默认独立导出。共享文件可复用，但每个页面实例都必须映射。

文字和动态数据保留原生绑定规格；图形采用原生或合并背景的例外，需要可复现规格/父资产映射及客户对当前UI版本的明确确认，不能仅写“CSS可画”“工程端自行替换”。动态灯态不得藏进静态背景。

使用 [元素盘点模板](hmi-ui-design/assets/element-inventory.template.json) 记录角色、状态、文件与例外。构建和验收核对登记覆盖；还需逐页对照HTML发现盘点本身漏项。旧清单无盘点时显示missing_legacy_inventory，不等于当前完整范围通过。三项客户确认前仍只交HTML，不提前PNG渲染或切片。

## 持续扩展配色与布局

简短提示词不需要独自承担内容策划。技能按 [页面内容配方](hmi-ui-design/references/content-library.md) 主动拟定每页任务、模块、数据/单位、状态与交互，再纳入C1确认。自带总览、手动、参数、报警、IO和维护六类参考，按需选用，不自动将每个项目扩成六页。

页面配方在 `references/page-recipes/` 分文件维护ID/版本，与配色、布局分开更新；[状态组件参考](hmi-ui-design/references/state-components.md) 提供通信、灯态、命令、参数、IO、仪表/棒图等使用模式。[内容计划模板](hmi-ui-design/assets/page-content-plan.template.md) 记录本次实际选择。C2使用同一代表页的实际内容比较布局色调，C3各页按任务组织。现有打样构建器仅支持总览型槽位，其他页面按配方另行实现HTML，不能声称已自动支持所有类型。

自带 3 个配色主题和 3 个布局方案，均为 `proposed` 候选，未标记为用户批准或现场验证通过。主题与布局独立维护，可组合使用。

新增方案时，在 `assets/themes/` 或 `assets/layouts/` 添加文件，再通过 [style-catalog.json](hmi-ui-design/assets/style-catalog.json) 注册 ID、版本和相对路径。打样清单显式指定所使用的 ID 与版本，项目选定后固定版本，避免库更新无意改变已有页面。

具体契约见 [方案库说明](hmi-ui-design/references/style-library.md)，参数收集与选型流程见 [参数引导](hmi-ui-design/references/design-intake.md)。

## 交互与验收范围

按钮 `s0` 表示常态，`s1` 表示按下反馈；瞬时按钮松开、取消、失焦或切页后复位。底板、图标、文字、指示状态与热区分别管理，保持公共状态栏、报警带和导航跨页一致。

这是 AI 界面设计技能与本地演示工具，不是 PLC 程序或真实设备工程。模拟输出强制不写入真实设备，按钮反馈不代表设备已执行。

文件与代码逻辑已有测试覆盖；真实浏览器渲染及现场验收尚未完成。当前自动工具的 `files-and-logic` 通过仅表示该范围通过；完整范围中未完成的浏览器环节保持 `blocked`，不能据此声称完整界面验收通过。详见 [自动验收说明](hmi-ui-design/references/automatic-acceptance.md)。

## 验证

本地验证维护资源、扩展注册、版本锁定、输入拒绝、实际打包与可信代码逻辑：

```sh
python -m unittest discover -s tests -v
```

仓库附带相同范围的自动检查工作流。工作流文件已提供，远端执行结果需在上传后查看；本地检查不包含真实浏览器或现场验收。

## 许可

许可证由仓库维护者另行指定。
