"""Maple 构建补丁：移除 NR 名称后缀，并补齐 Emacs Han 匹配所需 cmap。

仅在 MAPLE_NR_PATCH=1 时启用；补丁与上游不兼容时必须停止构建。
"""

import os
import sys
from pathlib import Path

PATCH_INSTALLED = False
REPRESENTATIVES = (0x3410, 0x4E10, 0x5B57, 0xFE30, 0xF900)
COMPAT = 0xF900
SAME_AS = 0x4E92  # 互，与 U+F900 为统一关系，不新增轮廓。
STANDARD_SUBTABLES = ((0, 3), (0, 4), (3, 1), (3, 10))


def fail(message):
    """报告补丁错误并终止进程。

    参数：message 为具体错误描述。
    返回：不返回，始终抛出 SystemExit，阻止构建或归档继续执行。
    副作用：输出 Actions error 并追加 Job Summary；Summary 无法写入时仍终止。
    """
    text = f"Maple runtime patch 失效，需要更新 patches/sitecustomize.py 后重试：{message}"
    # 避免动态错误文本中的换行和百分号破坏 Actions annotation 格式。
    annotation = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error::{annotation}", file=sys.stderr)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as output:
                output.write(f"\n## Maple runtime patch 需要更新\n\n{text}\n")
        except OSError as error:
            print(f"[runtime-patch] 无法写入 Job Summary：{error}", file=sys.stderr)
    raise SystemExit(text)


def patch_cjk_compat_fonts(output_dir):
    """归档前检查 CN 字体并补齐兼容映射。

    参数：output_dir 为上游字体输出目录。
    返回：None；必要时原地更新 CN 字体的 cmap，已兼容的字体不修改。
    异常：无法补齐代表字时抛出 SystemExit，读写错误交由调用方报告并终止。
    """
    from fontTools.ttLib import TTFont

    directory = Path(output_dir)
    if not directory.is_dir():
        fail(f"字体输出目录不存在：{directory}")
    patched, already_ok = 0, 0
    for path in directory.rglob("*.ttf"):
        if "CN" not in path.stem:
            continue
        font = TTFont(str(path))
        try:
            best = font.getBestCmap() or {}
            missing = [codepoint for codepoint in REPRESENTATIVES if codepoint not in best]
            if not missing:
                already_ok += 1
                continue
            if missing != [COMPAT] or SAME_AS not in best:
                fail(
                    f"{path.name} 无法可靠补齐 cmap，缺失代表字："
                    + ", ".join(f"U+{codepoint:04X}" for codepoint in missing)
                    + f"；需要同形参照 U+{SAME_AS:04X}"
                )
            glyph = best[SAME_AS]
            touched = []
            for subtable in font["cmap"].tables:
                encoding = (subtable.platformID, subtable.platEncID)
                if encoding in STANDARD_SUBTABLES and COMPAT not in subtable.cmap:
                    subtable.cmap[COMPAT] = glyph
                    touched.append((*encoding, subtable.format))
            best_after = font.getBestCmap() or {}
            still_missing = [
                codepoint for codepoint in REPRESENTATIVES if codepoint not in best_after
            ]
            if still_missing:
                fail(
                    f"{path.name} cmap 自检失败："
                    + ", ".join(f"U+{codepoint:04X}" for codepoint in still_missing)
                )
            font.save(str(path))
            patched += 1
            print(
                f"[cjk-compat] {path.name}: cmap[U+F900] -> {glyph!r} on {touched}",
                file=sys.stderr,
            )
        finally:
            font.close()
    if already_ok:
        print(f"[cjk-compat] {already_ok} 个 CN 字体已兼容，跳过", file=sys.stderr)
    if patched:
        print(f"[cjk-compat] 已为 {patched} 个 CN 字体补 U+F900", file=sys.stderr)


def install():
    """加载上游模块并安装幂等的命名及归档钩子。

    参数：无；上游根目录由 GITHUB_WORKSPACE 或当前工作目录决定。
    返回：None；修改上游类方法，不修改上游源码文件。
    异常：挂接点失效时抛出 SystemExit，其它异常由入口统一报告并终止。
    """
    root = os.environ.get("GITHUB_WORKSPACE") or os.getcwd()
    if os.path.isfile(os.path.join(root, "build.py")) and root not in sys.path:
        sys.path.insert(0, root)

    from scripts.config.resolver import BuildConfigResolver
    from scripts.pipeline.orchestrator import MapleBuildPipeline

    if not callable(getattr(BuildConfigResolver, "_apply_identity", None)):
        fail("上游已无可调用的 BuildConfigResolver._apply_identity")
    if not callable(getattr(MapleBuildPipeline, "archive_outputs", None)):
        fail("上游已无可调用的 MapleBuildPipeline.archive_outputs")

    if not getattr(BuildConfigResolver, "_nr_suffix_stripped", False):
        original_identity = BuildConfigResolver._apply_identity

        def apply_identity(self, config):
            """运行上游 identity 解析并去掉 NR 后缀，保留窄体宽度。

            参数：self 为上游 resolver；config 为待原地更新的构建配置。
            返回：上游方法的返回值；字段结构不兼容时报告错误并终止。
            """
            try:
                result = original_identity(self, config)
                family_name = config.identity.family_name
                if config.feature.width in ("narrow", "slim") and " NR" not in family_name:
                    fail(
                        "上游不再追加 NR 后缀，需确认后移除此补丁 "
                        f"(width={config.feature.width}, family={family_name})"
                    )
                config.identity.family_name = family_name.replace(" NR", "")
                config.identity.family_name_compact = (
                    config.identity.family_name_compact.replace("NR", "")
                )
                return result
            except Exception as error:  # noqa: BLE001 - 补丁边界统一报告后终止，不吞掉异常
                fail(f"字体命名补丁执行失败：{error}")

        BuildConfigResolver._apply_identity = apply_identity
        BuildConfigResolver._nr_suffix_stripped = True
        print("[nr-patch] 已去除 family name 的 NR 后缀", file=sys.stderr)

    if not getattr(MapleBuildPipeline, "_cjk_compat_patched", False):
        original_archive = MapleBuildPipeline.archive_outputs

        def archive_with_cjk_compat(self):
            """补齐 CN cmap 后调用上游归档，补丁失败时禁止归档。

            参数：self 为上游 MapleBuildPipeline 实例。
            返回：上游 archive_outputs 的返回值。
            """
            try:
                patch_cjk_compat_fonts(self.runtime_context.output_dir)
            except Exception as error:  # noqa: BLE001 - 补丁边界统一报告后终止，不吞掉异常
                fail(f"CJK 兼容映射补丁执行失败：{error}")
            return original_archive(self)

        MapleBuildPipeline.archive_outputs = archive_with_cjk_compat
        MapleBuildPipeline._cjk_compat_patched = True
        print("[cjk-compat] 已挂接归档钩子", file=sys.stderr)


if os.environ.get("MAPLE_NR_PATCH") == "1":
    try:
        install()
        PATCH_INSTALLED = True
    except Exception as error:  # noqa: BLE001 - sitecustomize 初始化错误必须转为致命退出
        fail(f"无法加载上游补丁：{error}")
