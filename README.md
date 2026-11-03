# HMI UI Design Skill 1.06

面向工业HMI的分层组件、交互HTML及工程素材设计技能。作者备注：工控北极熊（抖音）。

1.06基于1.05追加式生成版优化。核心变化是按真实依赖增量导出、相同草稿跳过写入、人工确认视觉效果，以及限制无依据的全量重建。技能版本为1.06，MCGS交接schema继续使用1.05。

## 目录

```text
hmi-ui-design/       可单独安装的完整技能
tests/               资源、流程、交付与真实浏览器增量测试
examples/            保留的功能原型及方向方案回归示例
.github/workflows/   仓库检查
CHANGELOG.md         相对1.03及1.05的变化
VERSION              1.06
requirements.txt     生产Python依赖
requirements-dev.txt 验证依赖
```

## 使用与安装

将整个`hmi-ui-design`目录放入使用端的本地技能目录，再调用`$hmi-ui-design`。检查实际读取的`SKILL.md`版本是1.06，revision为`2026-11-03-v106-mcgs-interface-r1`。保留旧版本及原项目证据，不替换正在运行的任务。源码包解压后可将本目录内容作为GitHub仓库根目录上传；安装包只包含技能文件夹。

Python工具需要3.12+和Pillow；批量渲染另需Node.js 22+及可用Chrome/Chromium。开发验证另需PyYAML。依赖按使用范围安装：

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Windows若`python`只是商店别名，使用已有解释器完整路径；不要反复尝试、搜索或自动安装。新建实际项目目录后，可用以下命令复用环境探测报告；硬件/驱动变化用`--refresh`，过期报告写新文件并返回实际路径。

```powershell
python hmi-ui-design/scripts/probe_render_environment.py --out project/render-environment.json --reuse
```

## MCGS接口修订

当前1.06还包含动作scope、数值输入类型、factory/native_type分流和按钮双态排版校验；机器协议版本保持原样。先在代表页用 `execution_profile.py --spec` 检查，再做正式资产输出。未支持的设计保留要求并逐项报告，不静默改成演示或外置文字。详细字段、命令及工程侧依赖见[接口兼容说明](hmi-ui-design/references/mcgs-interface-compatibility.md)。

默认不兼容即阻断正式导出。明确需要待适配符号要求时，使用 `--allow-symbolic-unsupported`；仅输出 `mcgs-plan.symbolic.json`，并附 `execution-compatibility.json`，不生成常规计划文件。通用配置不能证明实际模板或原厂运行通过。

## 接入增量生产

详细契约及输入字段见[增量生产](hmi-ui-design/references/incremental-generation.md)。

1. 草稿生成器先产生source-plan，把实际完整文本交给`sync_component_sources.py`；相同内容不写入，变化只替换对应草稿文件，旧文件不自动删除。完整项目传入workflow保护已确认快照。
2. 为组件提供独立、静态的导出HTML和必要共享CSS/母版。给原render manifest增加`optimization.static=true`、专用`source_root`及`cache_dir`，按实际环境设置backend_key或backend_report。
3. 每批仍用新输出目录；缓存对该文档实际加载的依赖内容、PNG结构/解码/哈希和尺寸逐项复核。只有命中项复用；共享源确实改变时，报告依赖及相应重跑范围。
4. 页面预览和DOM探测继续实际执行，最终完整库存对账保留。人工确认视觉效果；AI只集中修复具体机械问题，不反复审美改稿。

```powershell
python hmi-ui-design/scripts/sync_component_sources.py --plan project/source-plan.json --draft-root project/draft --workflow project/workflow.json
node hmi-ui-design/scripts/render_components.mjs project/render-manifest.json project/render/new-batch
```

可用`prepare_render_manifest.py`从同一delivery几何数据派生渲染清单及对应delivery输入，减少重复维护尺寸和文件路径；MCGS业务字段继续通过既有handoff输入与导出器验证。

**旧任务接入说明**：安装1.06不会自动重写已有自编生成器。若旧入口仍清空目录、重写所有源、每次全量调用渲染器，就必须先把这些调用接入上述工具，并确认当前任务实际加载1.06。仅换批次目录或只修改提示词不等于已经实现增量。

动态原型、时间/随机数、网络资源及持续动画不能声明为静态缓存源。旧manifest仍可兼容运行，但不自动启用缓存。未变化素材复用不等于当前浏览器/GPU/原厂运行已验证；报告分别记录检查范围。

## 检查与测试

从仓库根目录运行；测试素材与客户项目分开。生产生成链不递归删除历史，新增增量测试和基准测试保留自己的证据目录。继承的回归测试仅清理各自临时测试夹具。

```powershell
python -X utf8 -B -m unittest discover -s tests -v
```

真实浏览器测试需要设置`HMI_TEST_BROWSER`，否则该组会明确跳过；`HMI_TEST_NODE`可指定Node路径，`HMI_TEST_WORK`可指定测试产物目录。GitHub检查会定位浏览器，确保这组实际运行。

```powershell
$env:HMI_TEST_BROWSER = '本机Chrome或Chromium可执行文件完整路径'
$env:HMI_TEST_WORK = '本次隔离测试目录'
python -X utf8 -B -m unittest discover -s tests -v
```

以下是合成静态素材基准，排除模型规划、设备绘制、人工等待和真实项目运行。默认7份源文档、260个捕获项，保留所有批次，比较首次/不变/单源变化；可指定1.05的原渲染器进行直接比较。RGB默认仅允许1/255渐变舍入误差，alpha必须一致，`--rgb-tolerance 0`要求完全一致。

```powershell
python -X utf8 -B tests/benchmark_incremental.py --browser '本机浏览器路径' --out '新的隔离基准目录'
```

测试通过只证明声明范围。人工视觉、真实交互以及MCGS原厂显示/运行未完成时继续列待验，不修改报告冒充通过。
