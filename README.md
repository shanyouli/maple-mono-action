# Maple Mono 自定义构建

通过 GitHub Actions 从上游 [subframe7536/maple-font](https://github.com/subframe7536/maple-font) 的 `variable` 分支（V8 开发版）自动构建自定义 Maple Mono 字体。无需 fork 上游仓库。

## 使用

1. 将本仓库推送到你的 GitHub 仓库。
2. 进入仓库 **Actions** 页面，若提示禁用则先启用 workflows。
3. 选择 **🍁 Build Maple Mono** → **Run workflow** 手动触发；或等待每周一 11:00（北京时间）定时构建。
4. 构建完成后：
   - **Actions → 该次运行 → Artifacts** 下载（保留 30 天）；
   - 或 **Releases** 页面下载 `v8-<上游短SHA>` 版本（永久保留，可追溯到上游源码 commit）。

定时构建时若上游 `variable` 分支无新提交，将自动跳过；手动触发时可勾选 `force` 强制重建。

## 构建配置

```
# 第一遍：静态输出（含静态 NF 8×2，为静态 NF-CN 合并提供 base；上游要求 NF 可变必须与 CJK 可变同遍，故 --nf-variable 只能在第二遍）
python build.py --cjk cn --cjk-both --nf --nf-mono --legacy-thin-weight-class --width narrow --format ttf --line-height 0.886 --feat cv02,cv03,cv05,cv09,cv10,ss03,ss07,ss08,ss09,ss10,ss11 --archive
# 第二遍：可变输出（NF 可变 + 中文可变；--cache 复用第一遍产物）
python build.py --cjk cn --cjk-both --nf --nf-mono --legacy-thin-weight-class --width narrow --format ttf --line-height 0.886 --feat cv02,cv03,cv05,cv09,cv10,ss03,ss07,ss08,ss09,ss10,ss11 --nf-variable --cjk-variable --archive --cache
```

| 配置 | 选择 | 说明 |
|---|---|---|
| `--width narrow` | ✅ | 字形宽度 550（默认 600） |
| `--nf` | ✅ | Nerd Font 图标（默认已开启，显式声明） |
| `--nf-mono` | ✅ | NF 图标强制单宽（默认图标宽度约 1.6–1.8 cell），终端列对齐更稳 |
| `--nf-variable` | ✅ | NF 以可变字体输出，替代「8 字重 × 2」的静态组合（仅第二遍） |
| 字体名 patch | ✅ | workflow 移除 family 名中的 NR 后缀：保留 narrow(550) 宽度，但字体名为 Maple Mono / NF / CN / NF CN |
| `--legacy-thin-weight-class` | ✅ | Thin/ExtraLight 用 250/275 老式 weightClass，规避 Windows JetBrains IDE 的 GDI 假粗 |
| `--cjk cn` | ✅ | 简体中文版（含常用繁中/日文区段） |
| `--cjk-both` | ✅ | 同时产出 CN 无图标版 + NF CN 有图标版 |
| `--format ttf` | ✅ | 仅静态 ttf（拉丁可变字体默认总是构建） |
| `--line-height 0.886` | ✅ | 行高对齐 LXGW WenKai Mono（1.170 em，默认 1.32 em 偏高；hhea/OS\2 三表统一生效） |
| `--cjk-variable` | ✅ | 第二次构建，中文输出为可变字体 |
| `--feat cv02,cv03,cv05,cv09,cv10,ss03,ss07,ss08,ss09,ss10,ss11` | ✅ | Playground 实测选定：`a/i/g/7/Z z` 替代字形 + 标签任意大小写 + 箭头/等号类连字增强 |
| `--cjk-hinted` | ❌ | 中文 auto-hint 保持默认关闭：仅低 DPI + Windows GDI 小字号有收益，高 DPI 下会引入形变且显著拉长构建时间 |
| 中文间距 | 默认 2:1 | 未加 `--cjk-narrow`（会破坏等宽识别） |
| 字形风格 | Maple 默认 | 未加 `--normal`（JetBrains 风格预设） |
| 连字 | 全部保留 | 未加 `--no-liga` / `--remove-tag-liga` |

## 产物结构

```
static/                      第一次构建（静态）
├── MapleMono-*.zip          纯拉丁，8 字重 × 直/斜体
├── MapleMono-Variable-*.zip 纯拉丁可变字体（单文件全字重）
├── MapleMono-NF-*.zip       + Nerd Font 图标
├── MapleMono-NF-CN-*.zip    + 简体中文 + 图标
└── MapleMono-CN-*.zip       + 简体中文（无图标）
variable/                    第二次构建（中文可变）
└── MapleMono-CN-Variable-*.zip 等中文可变字体包
```

> 基于 `--nf-variable`，NF 家族会以可变字体形式产出（而非 8 字重静态组合）；实际命名以首次运行后的产物清单为准。

> 压缩包文件名以上游实际输出为准，`--archive` 打包时自动附上 config 与 license。

## 调整配置

编辑 [`.github/workflows/build-maple.yml`](.github/workflows/build-maple.yml) 顶部的 `BUILD_ARGS` 环境变量即可。常用可选项：

- `--cjk-narrow`：中文紧凑间距（代价：不再被识别为严格等宽字体）
- `--cjk-hinted`：对最终静态中文包做 auto-hint（低 DPI Windows 才有收益）
- `--no-hinted`：改用未 hint 的拉丁 base（高 DPI / Retina / macOS 下观感更干净）
- `--normal`：JetBrains Mono 风格预设（斜线 0、去除个性化字形）
- `--feat zero,cvXX,ssXX,...`：冻结更多 OpenType 特性（特性清单见上游 `sources/schema.json`）
- `--cjk-scale-factor 1.03`：放大中文字形（>1 放大，缓解「中文字间距偏大」；也可写成 `1.03,1.0`）
- `--nf-propo`：NF 图标改回可变宽度（覆盖 `--nf-mono`，适合非等宽场景）
- `--remove-tag-liga`：移除 `[TODO]` 等纯文本标签连字
- `--line-height 1.1`：行高系数（当前 0.886 对齐 LXGW WenKai Mono，可投喜好微调）
- `--least-styles`：只构建 Regular/Bold/Italic/BoldItalic 四个样式
- `--format ttf,woff2`：额外输出 woff2（供网页/在线 IDE 使用，体积约为 ttf 的一半）

> ⚠️ 上游 `variable` 分支为 V8 开发版，构建行为与产物命名可能随上游变动。
