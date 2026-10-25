# 矩形切片助手

`scripts/slice_assets.py` 只裁切已有、已获授权的 PNG。坐标来自人工确认的 manifest；不生图、不识别组件、不抠背景、不缩放、不补边、不推断边界。先审核源图和矩形，再运行工具。不得把模型给出的估计坐标直接当成验收通过。

## 依赖与命令

- Python 3.12+、Pillow；不依赖网络。入口会明确拒绝旧版 Python，以保证 Windows junction 检查可用。当前环境已验证 Python 3.12.14、Pillow 12.3.0。
- 输入为静态 PNG，支持 `1/L/LA/P/RGB/RGBA` 模式；RGBA 的像素与透明度逐像素保留。直接读取 PNG IHDR 检查原始位深，拒绝 16 位 PNG（包括可能被 Pillow 解码成 8 位模式的 RGB/RGBA）。不接受带旋转 EXIF 的 PNG，请在确定坐标之前另行规范化。
- 命令中的 `python` 应指向实际可用的 Python；本机捆绑解释器见根目录环境记录，不依赖 Windows 商店别名。

```powershell
python .\scripts\slice_assets.py --manifest .\assets\slice-manifest.json --out .\exports\panel --dry-run
python .\scripts\slice_assets.py --manifest .\assets\slice-manifest.json --out .\exports\panel
```

`--dry-run` 完整读取、校验、内存裁切并编码 PNG，向标准输出返回 JSON 报告，**不创建文件或目录**。正式运行会写 PNG 和固定文件名 `slice-report.json`，并输出同一报告。退出码 `0` 表示成功；`2` 表示校验或读写失败，标准错误输出包含 JSON 错误对象。命令行参数错误由 Python 参数解析器输出。

## Manifest 1.0

文件为 UTF-8 JSON。下例的源图必须真实存在，且恰为 `320 × 96` 像素；该例只是契约示例，不是已经验收的素材。

```json
{
  "schema_version": "1.0",
  "source": "approved/button-atlas.png",
  "canvas_px": [320, 96],
  "assets": [
    {
      "id": "button_start_normal",
      "file": "buttons/start_normal.png",
      "rect_px": [0, 0, 160, 96],
      "state": "normal",
      "expected_size_px": [160, 96],
      "alpha_required": true,
      "padding_px": [8, 8, 8, 8],
      "same_canvas_group": "button_start"
    },
    {
      "id": "button_start_pressed",
      "file": "buttons/start_pressed.png",
      "rect_px": [160, 0, 160, 96],
      "state": "pressed",
      "expected_size_px": [160, 96],
      "alpha_required": true,
      "padding_px": [8, 8, 8, 8],
      "same_canvas_group": "button_start"
    }
  ]
}
```

| 字段 | 契约 |
| --- | --- |
| `schema_version` | 必须为字符串 `"1.0"`。 |
| `source` | 相对 manifest 所在目录的源 PNG；只读取，不覆盖。禁止绝对路径、`..`、链接跳转。 |
| `canvas_px` | `[宽, 高]`，必须与读取到的真实像素尺寸完全一致。 |
| `assets` | 非空数组；每项必须包含 `id/file/rect_px/state/expected_size_px/alpha_required`。 |
| `id` | 非空字符串，忽略大小写后唯一；建议使用项目命名规范。 |
| `file` | 相对 `--out` 的 `.png` 路径；建议 ASCII 小写文件名。 |
| `rect_px` | `[x, y, 宽, 高]`，左上为 `(0,0)`；左闭右开、上闭下开；整数像素，不接受小数或布尔值，宽高大于 0，矩形不得越界。 |
| `state` | 非空状态名，如 `normal/pressed/disabled/alarm`；工具不替项目推断状态。 |
| `expected_size_px` | 必须恰等于矩形的宽高；不匹配即失败，绝不缩放来适配。 |
| `alpha_required` | 必须为布尔值；`true` 要求裁片至少有 1 个 alpha 小于 255 的像素。仅有全不透明的 RGBA 通道不能通过该检查。 |
| `padding_px` | 可选 `[左,上,右,下]`，默认 `[0,0,0,0]`；记录**已经包含在矩形内**的留白，不添加像素，也不假设其一定透明。需留出正宽高的内容区域。 |
| `same_canvas_group` | 可选非空字符串；同组所有状态的画布宽高必须相同，状态名忽略大小写后不得重复。组名忽略大小写。 |

未知字段、重复 JSON 键、重复 id/路径和 `NaN/Infinity` 都会报错，避免拼写错误被静默忽略。路径同时识别 `/` 和 `\`，拒绝绝对路径、盘符、空段、`.`、`..`、Windows 设备名、非法字符及末尾空格/句点。每个输出文件的路径忽略大小写后必须唯一，并拒绝文件/目录相互冲突。

## 透明度、同画布与留白

输出保持源图裁片的图像模式与像素；保存后重新解码，逐像素对比 RGBA 值。调色板 PNG 的透明信息也会验证。PNG 压缩和元数据可能与原文件不同；本工具的保证是像素值，不保证原编码字节不变。源文件始终只读。

同画布只验证尺寸和组内状态唯一性，不验证按钮轮廓、图标锚点或视觉位置一致。设计人员仍须叠图检查。源图若没有准确的留白、对齐或透明背景，先修订源素材及 manifest，不能用切片工具补造。`content_rect_px` 是裁片内部去除所声明 padding 后的区域；它是元数据，不是自动识别的实际内容边界。

## 报告与失败边界

报告包含源图/manifest SHA-256、源画布尺寸及 IHDR 位深、各输出的 SHA-256/字节数/真实尺寸/状态/矩形/留白/透明像素统计及 PNG 回读校验结果。透明统计区分 alpha 为 `0`、`1–254`、`255` 的像素数，记录 alpha 极值、显式 alpha 通道和透明元数据。dry-run 报告状态为 `dry_run_ok`，单项为 `validated`；正式写出为 `written`。

所有裁片在内存里完成校验和编码后才写出。输出目录必须与源图及 manifest 隔离，不能把包含输入的目录作为 `--out`；已有输出、已有报告一律拒绝覆盖，请换一个导出目录。输出目录、其祖先及子路径不得含符号链接或 Windows junction；在解析真实路径之前检查祖先，dry-run 同样拒绝。独占创建防止覆盖校验后的竞态文件；普通写入异常会回滚本次创建的文件及空目录。断电、强制终止或外部进程同时修改目录不具备事务保证，导出时应独占目标目录。

切片通过只代表几何、文件和像素校验通过；**不代表 UI 视觉验收、状态语义、安全规范或目标 HMI 软件导入验收通过**。
