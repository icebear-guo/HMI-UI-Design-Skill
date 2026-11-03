"""校验「设计 → 工程」交付物是否合规（命名 + 控件映射）。

    python pro_check_handoff.py --slices 切图目录 [--manifest 清单.csv]

仅用于旧版清单迁移；新组件源交付使用 export_handoff.py。
规则由本技能 references/mcgs-export-profile.md 维护：
  · 资产名只允许 A-Z a-z 0-9 _，且必须是 .png
  · 数值控件需变量；静态图片使用图片类型，不绑定变量
  · 类型必须是允许集合；同一行图名要能被图库引用
退出码 0 合规 / 1 有违规。输出 JSON。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")                      # 资产名：严格 ASCII
CTRL_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]+$")         # 控件名：允许中文，符号只准 _
TYPES = {"图片", "按钮", "数值输入", "数值显示", "指示灯", "状态切换", "标签", "矩形", "圆角矩形"}
NUMERIC_TYPES = {"数值输入", "数值显示"}
COLS = ["页名", "控件名", "类型", "图s0", "图s1", "x", "y", "w", "h",
        "文字", "变量", "单位", "小数位", "最小值", "最大值", "跳转"]


def check_slices(folder):
    bad, ok = [], 0
    META = {".csv", ".json", ".txt", ".md", ".html", ".htm", ".xml"}
    for p in sorted(Path(folder).rglob("*")):
        if not p.is_file() or p.suffix.lower() in META:
            continue
        stem = p.stem
        if not NAME_RE.match(stem):
            bad.append({"file": str(p.relative_to(folder)), "reason": "文件名含非法字符"})
        elif p.suffix != ".png":
            bad.append({"file": str(p.relative_to(folder)),
                        "reason": f"扩展名必须是小写 .png，实际 {p.suffix or '无扩展名'}"})
        else:
            ok += 1
    return {"ok": ok, "violations": bad}


def png_size(path):
    """读 PNG 的 IHDR 拿宽高，不依赖第三方库。"""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def check_size_match(folder, rows):
    """清单里的 w/h 必须与切图实际像素一致——用来抓"倍数切图"。"""
    root = Path(folder)
    index = {p.stem: p for p in root.rglob("*.png")}
    bad = []
    for i, r in enumerate(rows, 2):
        stem = (r.get("图s0") or "").strip()
        if not stem:
            continue
        src = index.get(stem)
        if src is None:
            bad.append({"row": i, "reason": f"切图 {stem}.png 不存在于目录"})
            continue
        size = png_size(src)
        if size is None:
            bad.append({"row": i, "reason": f"{stem}.png 不是有效 PNG"})
            continue
        try:
            w, h = int(r["w"]), int(r["h"])
        except (KeyError, ValueError):
            continue
        if (w, h) != size:
            ratio = size[0] / w if w else 0
            hint = f"，疑似 {ratio:.0f} 倍切图" if ratio >= 1.9 else ""
            bad.append({"row": i, "reason": f"{stem}.png 实际 {size[0]}×{size[1]} 像素，"
                                              f"清单为 {w}×{h}{hint}"})
    return bad


def check_manifest(path, strict_ctrl=False):
    rows = list(csv.DictReader(Path(path).open(encoding="utf-8-sig")))
    if not rows:
        return {"violations": [{"row": 0, "reason": "清单为空"}]}
    header = list(rows[0].keys())
    missing = [c for c in COLS if c not in header]
    if missing:
        return {"violations": [{"row": 0, "reason": f"缺列 {missing}"}]}

    bad = []
    for i, r in enumerate(rows, 2):
        name = (r.get("控件名") or "").strip()
        kind = (r.get("类型") or "").strip()
        pat = NAME_RE if strict_ctrl else CTRL_RE
        if not pat.match(name):
            hint = "只允许 A-Za-z0-9_" if strict_ctrl else "只允许字母数字中文和下划线"
            bad.append({"row": i, "reason": f"控件名 {name!r} 含非法字符（{hint}）"})
        if kind not in TYPES:
            bad.append({"row": i, "reason": f"类型 {kind!r} 不在允许集合"})
            continue
        for col in ("图s0", "图s1"):
            v = (r.get(col) or "").strip()
            if v and not NAME_RE.match(v):
                bad.append({"row": i, "reason": f"{col} {v!r} 含非法字符"})
        var = (r.get("变量") or "").strip()
        if kind in NUMERIC_TYPES and not var:
            bad.append({"row": i, "reason": "数值类控件未绑定变量（设计要求：数值位置必须绑变量）"})
        if kind == "图片" and var:
            bad.append({"row": i, "reason": f"静态图片图库引用不是变量绑定，实际绑了 {var!r}"})
        for col in ("x", "y", "w", "h"):
            v = (r.get(col) or "").strip()
            if v and not v.isdigit():
                bad.append({"row": i, "reason": f"{col}={v!r} 不是整数"})
    return {"rows": len(rows), "violations": bad}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slices")
    ap.add_argument("--manifest")
    ap.add_argument("--strict", action="store_true", help="控件名也强制 ASCII")
    a = ap.parse_args()
    if not a.slices and not a.manifest:
        print(json.dumps({"status": "error", "message": "至少给 --slices 或 --manifest"}))
        raise SystemExit(1)

    report = {}
    bad = 0
    if a.slices:
        report["slices"] = check_slices(a.slices)
        bad += len(report["slices"]["violations"])
    if a.manifest:
        report["manifest"] = check_manifest(a.manifest, a.strict)
        bad += len(report["manifest"]["violations"])
        if a.slices:
            rows = list(csv.DictReader(Path(a.manifest).open(encoding="utf-8-sig")))
            mism = check_size_match(a.slices, rows)
            report["size_match"] = {"violations": mism}
            bad += len(mism)
    report["status"] = "pass" if bad == 0 else "fail"
    report["violations"] = bad
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
