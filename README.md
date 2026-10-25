# HMI UI Design Skill｜工业人机界面设计技能

面向工业触摸屏、设备操作面板与监控画面的 AI 设计技能，覆盖需求引导、配色与布局打样、分层组件、按钮双态切片、可交互 HTML 原型和分范围验收。

先让使用者选择设计方向，再展开完整页面。技能以通用规范、可更新的方案库、模板和本地构建工具组成，可配合支持 `SKILL.md` 的 AI 工具使用。

## 使用流程

1. **收集必要参数**：先读取已有资料，再补问原生分辨率、物理尺寸、横竖屏、目标平台、输入方式、页面内容、导航位置与数量、浅色或深色等缺项。允许“不确定，先建议”，暂定值独立标识。
2. **首次同页打样**：方向未定时，默认先生成同一代表页面的 3 种 HTML 候选。各方案保持相同画布、内容与数据，比较实际布局和色调差异。
3. **选择或混选**：可以选一个完整方案，也可以选“方案 A 的布局 + 方案 B 的配色”。保留方案 ID、版本及明确的选择记录；方向未选定时，不批量展开其余页面。
4. **完成设计与交互**：沿用选定参数制作页面、分层组件和 `s0/s1` 按钮切片，实现灯与 IO 切换、模拟输出强制、导航、参数输入、仪表和棒图联动等适用功能。
5. **检查与交付**：交付离线 HTML、设计标注、页面预览、独立切片、资源清单和 ZIP。文件、代码逻辑、真实浏览器及现场验收分别记录。

已有明确设计系统或只要求局部修改、单项素材、规范评审时，按实际任务执行，无需重复选型。

## 目录

```text
.
├─ hmi-ui-design/
│  ├─ SKILL.md                 技能入口
│  ├─ agents/                  工具界面元数据
│  ├─ references/              参数引导、设计、交互、交付与验收规则
│  ├─ assets/
│  │  ├─ style-catalog.json     配色与布局方案注册表
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

> 使用 hmi-ui-design 为设备设计 1024×600 横屏界面。先确认必要参数，再用同一个总览页面提供浅色和深色、不同导航布局的 HTML 样例。选定方向后再制作其余页面，并交付按钮 s0/s1 切片和可操作原型。

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

使用自带输入生成完整交互样包：

```sh
python hmi-ui-design/scripts/build_delivery.py --manifest examples/interactive-preview/inputs/delivery-manifest.json --out exports/hmi-ui-delivery
```

打开 `exports/hmi-ui-delivery/index.html`，在交互演示与设计标注间切换。也可打开自带的 [两页交互样例](examples/interactive-preview/delivery/index.html)。交付清单模板引用实际 PNG 文件，换成自己的设计时需同时提供对应页面与独立资产。

运行文件与纯代码逻辑检查：

```sh
python hmi-ui-design/scripts/accept_delivery.py --package exports/hmi-ui-delivery --node node --scope files-and-logic
```

执行完整范围报告：

```sh
python hmi-ui-design/scripts/accept_delivery.py --package exports/hmi-ui-delivery --node node --scope complete
```

输出目录及同名 ZIP 必须不存在，工具不会覆盖旧交付。再次构建时使用新的输出名称。验收报告保存在交付目录外。

## 持续扩展配色与布局

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
