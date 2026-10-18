# Maple Mono 自定义构建

通过 GitHub Actions 从上游 [subframe7536/maple-font](https://github.com/subframe7536/maple-font) 的 `variable` 分支（V8 开发版）自动构建自定义 Maple Mono 字体。无需 fork 上游仓库。

## 使用

1. 将本仓库推送到你的 GitHub 仓库。
2. 进入仓库 **Actions** 页面，若提示禁用则先启用 workflows。
3. 选择 **Build Maple Mono** → **Run workflow** 手动触发；或等待每周一 11:00（北京时间）定时构建。
4. 构建完成后：
   - **Actions → 该次运行 → Artifacts** 下载（保留 30 天）；
   - 或 **Releases** 页面下载 `v8-<上游短SHA>` 版本（永久保留，可追溯到上游源码 commit）。

定时构建时若上游 `variable` 分支无新提交，将自动跳过；手动触发时可勾选 `force` 强制重建。

## 构建配置

```
python build.py --cjk cn --cjk-both --nf --width narrow --format ttf --line-height 0.886 --feat cv02,cv03,cv05,cv09,cv10,ss03,ss07,ss08,ss09,ss10,ss11 --archive
python build.py --cjk cn --cjk-both --nf --width narrow --format ttf --line-height 0.886 --feat cv02,cv03,cv05,cv09,cv10,ss03,ss07,ss08,ss09,ss10,ss11 --cjk-variable --archive --cache
```

| 配置 | 选择 | 说明 |
|---|---|---|
| `--width narrow` | ✅ | 字形宽度 550（默认 600） |
| `--nf` | ✅ | Nerd Font 图标（默认已开启，显式声明） |
| `--cjk cn` | ✅ | 简体中文版（含常用繁中/日文区段） |
| `--cjk-both` | ✅ | 同时产出 CN 无图标版 + NF CN 有图标版 |
| `--format ttf` | ✅ | 仅静态 ttf（拉丁可变字体默认总是构建） |
| `--line-height 0.886` | ✅ | 行高对齐 LXGW WenKai Mono（1.170 em，默认 1.32 em 偏高；hhea/OS\2 三表统一生效） |
| `--cjk-variable` | ✅ | 第二次构建，中文输出为可变字体 |
| `--feat cv02,cv03,cv05,cv09,cv10,ss03,ss07,ss08,ss09,ss10,ss11` | ✅ | Playground 实测选定：`a/i/g/7/Z z` 替代字形 + 标签任意大小写 + 箭头/等号类连字增强 |
| 中文间距 | 默认 2:1 | 未加 `--cjk-narrow` |
| 字形风格 | Maple 默认 | 未加 `--normal`（JetBrains 风格预设） |
| 连字 | 全部保留 | 未加 `--no-liga` / `--remove-tag-liga` |

## 产物结构

```
static/                      第一次构建（静态）
├── MapleMono-*.zip          纯拉丁，8 字重 × 直/斜体
├── MapleMono-Variable-*.zip 纯拉丁可变字体（单文件全字重）
├── MapleMono-NF-*.zip       + Nerd Font 图标
├── MapleMono-CN-*.zip       + 简体中文（无图标）
└── MapleMono-NF-CN-*.zip    + 简体中文 + 图标
variable/                    第二次构建（中文可变）
└── MapleMono-CN-Variable-*.zip 等中文可变字体包
```

> 压缩包文件名以上游实际输出为准，`--archive` 打包时自动附上 config 与 license。

## 调整配置

编辑 [`.github/workflows/build-maple.yml`](.github/workflows/build-maple.yml) 顶部的 `BUILD_ARGS` 环境变量即可。常用可选项：

- `--cjk-narrow`：中文紧凑间距（代价：不再被识别为严格等宽字体）
- `--normal`：JetBrains Mono 风格预设（斜线 0、去除个性化字形）
- `--feat zero,cvXX,ssXX,...`：冻结更多 OpenType 特性（特性清单见上游 `sources/schema.json`）
- `--nf-mono`：Nerd Font 图标强制单字符等宽
- `--remove-tag-liga`：移除 `[TODO]` 等纯文本标签连字
- `--line-height 1.1`：行高系数（当前 0.886 对齐 LXGW WenKai Mono，可投喜好微调）
- `--least-styles`：只构建 Regular/Bold/Italic/BoldItalic 四个样式

> ⚠️ 上游 `variable` 分支为 V8 开发版，构建行为与产物命名可能随上游变动。
