"""验证 runtime patch 的启动保护、命名兼容性和 CJK 归档行为。

运行：uv run --with fonttools --with pyyaml python -m unittest discover -s tests -v
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches"
REPRESENTATIVES = (0x3410, 0x4E10, 0x5B57, 0xFE30, 0xF900)


class RuntimePatchTests(unittest.TestCase):
    """通过独立 Python 进程验证 sitecustomize 启动及失败退出。"""

    def setUp(self):
        """无参数；为每个测试建立独立的上游源码与输出临时目录。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.upstream = Path(self.temp.name)
        self.summary = self.upstream / "summary.md"
        self.fonts = self.upstream / "fonts"
        self.fonts.mkdir()
        (self.upstream / "build.py").write_text("", encoding="utf-8")
        for directory in ("scripts", "scripts/config", "scripts/pipeline"):
            path = self.upstream / directory
            path.mkdir(exist_ok=True)
            (path / "__init__.py").write_text("", encoding="utf-8")
        self.resolver = self.upstream / "scripts/config/resolver.py"
        self.resolver.write_text(
            "class BuildConfigResolver:\n"
            "    def _apply_identity(self, config):\n"
            "        return 42\n",
            encoding="utf-8",
        )
        self.pipeline = self.upstream / "scripts/pipeline/orchestrator.py"
        self.pipeline.write_text(
            "from pathlib import Path\n"
            "class MapleBuildPipeline:\n"
            "    def archive_outputs(self):\n"
            "        Path('archived').touch()\n"
            "        return 42\n",
            encoding="utf-8",
        )

    def run_patch(self, code="print('MAIN_EXECUTED')", enabled=True):
        """参数为主程序代码及启用开关；返回捕获输出的子进程执行结果。"""
        env = os.environ.copy()
        env.update(
            PYTHONPATH=str(PATCHES),
            GITHUB_WORKSPACE=str(self.upstream),
            GITHUB_STEP_SUMMARY=str(self.summary),
            MAPLE_NR_PATCH="1" if enabled else "0",
            PYTHONDONTWRITEBYTECODE="1",
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=self.upstream,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def assert_patch_failed(self, result):
        """参数为子进程结果；断言构建未继续且已输出 Actions 错误与 Summary。"""
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("MAIN_EXECUTED", result.stdout)
        self.assertIn("::error::", result.stderr)
        self.assertIn("需要更新", self.summary.read_text(encoding="utf-8"))
        self.assertFalse((self.upstream / "archived").exists())

    def create_font(self, codepoints):
        """参数为字体 cmap 的码点集合；返回生成的最小 CN TTF 路径。"""
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder([".notdef", "han"])
        builder.setupCharacterMap({codepoint: "han" for codepoint in codepoints})
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.closePath()
        builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "han": pen.glyph()})
        builder.setupHorizontalMetrics({".notdef": (1000, 0), "han": (1000, 0)})
        builder.setupHorizontalHeader(ascent=904, descent=-266)
        builder.setupNameTable({"familyName": "Maple Mono CN", "styleName": "Regular"})
        builder.setupOS2(sTypoAscender=904, sTypoDescender=-266)
        builder.setupPost()
        path = self.fonts / "MapleMono-CN-Test.ttf"
        builder.save(path)
        return path

    def archive(self):
        """无参数；返回调用补丁后上游归档方法的子进程结果。"""
        return self.run_patch(
            "from types import SimpleNamespace\n"
            "from scripts.pipeline.orchestrator import MapleBuildPipeline\n"
            "pipeline = MapleBuildPipeline()\n"
            "pipeline.runtime_context = SimpleNamespace(output_dir='fonts')\n"
            "assert pipeline.archive_outputs() == 42\n"
            "print('MAIN_EXECUTED')\n"
        )

    def test_disabled_patch_does_not_import_upstream(self):
        """关闭开关时不加载上游，返回成功且不产生错误 Summary。"""
        self.resolver.unlink()
        result = self.run_patch(enabled=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.summary.exists())

    def test_startup_failure_stops_main(self):
        """上游模块缺失时 Python 启动失败，主程序不会执行。"""
        self.resolver.unlink()
        self.assert_patch_failed(self.run_patch())

    def test_unexpected_import_error_stops_main(self):
        """非 ImportError 初始化异常也须转换为致命退出。"""
        self.resolver.write_text("raise RuntimeError('upstream changed')\n", encoding="utf-8")
        self.assert_patch_failed(self.run_patch())

    def test_missing_archive_hook_stops_main(self):
        """上游归档方法缺失时拒绝运行主程序。"""
        self.pipeline.write_text("class MapleBuildPipeline: pass\n", encoding="utf-8")
        self.assert_patch_failed(self.run_patch())

    def test_noncallable_identity_hook_stops_main(self):
        """上游命名挂接点不再可调用时拒绝运行主程序。"""
        self.resolver.write_text(
            "class BuildConfigResolver: _apply_identity = 42\n", encoding="utf-8"
        )
        self.assert_patch_failed(self.run_patch())

    def test_nr_name_is_removed_without_changing_width(self):
        """兼容上游时移除 NR 名称、保留窄体配置，并允许重复安装。"""
        result = self.run_patch(
            "import sitecustomize\n"
            "sitecustomize.install()\n"
            "assert sitecustomize.PATCH_INSTALLED\n"
            "from types import SimpleNamespace as S\n"
            "from scripts.config.resolver import BuildConfigResolver\n"
            "config = S(feature=S(width='narrow'), "
            "identity=S(family_name='Maple Mono NR', family_name_compact='MapleMonoNR'))\n"
            "assert BuildConfigResolver()._apply_identity(config) == 42\n"
            "assert config.identity.family_name == 'Maple Mono'\n"
            "assert config.identity.family_name_compact == 'MapleMono'\n"
            "assert config.feature.width == 'narrow'\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_obsolete_name_patch_fails(self):
        """上游已移除 NR 后缀时要求维护者更新补丁。"""
        result = self.run_patch(
            "from types import SimpleNamespace as S\n"
            "from scripts.config.resolver import BuildConfigResolver\n"
            "config = S(feature=S(width='narrow'), "
            "identity=S(family_name='Maple Mono', family_name_compact='MapleMono'))\n"
            "BuildConfigResolver()._apply_identity(config)\n"
        )
        self.assert_patch_failed(result)

    def test_identity_field_change_fails(self):
        """上游 identity 字段变化时输出更新提示，不继续构建。"""
        result = self.run_patch(
            "from types import SimpleNamespace as S\n"
            "from scripts.config.resolver import BuildConfigResolver\n"
            "BuildConfigResolver()._apply_identity(S())\n"
        )
        self.assert_patch_failed(result)

    def test_cjk_mapping_is_persisted_and_idempotent(self):
        """兼容映射保存后保持轮廓不变，重复归档不再改写字体。"""
        path = self.create_font([*REPRESENTATIVES[:-1], 0x4E92])
        result = self.archive()
        self.assertEqual(result.returncode, 0, result.stderr)
        with TTFont(path) as font:
            cmap = font.getBestCmap()
            self.assertEqual(cmap[0xF900], cmap[0x4E92])
            self.assertTrue(all(cp in cmap for cp in REPRESENTATIVES))
        before = path.read_bytes()
        result = self.archive()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_already_compatible_font_is_not_modified(self):
        """代表字全部覆盖时无须 U+4E92，跳过补丁并保持文件不变。"""
        path = self.create_font(REPRESENTATIVES)
        before = path.read_bytes()
        result = self.archive()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_missing_source_glyph_prevents_archive(self):
        """缺少同形参照时不再仅发警告，必须阻止归档。"""
        self.create_font(REPRESENTATIVES[:-1])
        self.assert_patch_failed(self.archive())

    def test_other_missing_representative_prevents_archive(self):
        """兼容映射不能补救其它代表字缺失，必须阻止归档。"""
        self.create_font([*REPRESENTATIVES[1:], 0x4E92])
        self.assert_patch_failed(self.archive())

    def test_invalid_font_prevents_archive(self):
        """字体读取失败时输出补丁提示并阻止归档。"""
        (self.fonts / "MapleMono-CN-Test.ttf").write_bytes(b"invalid font")
        self.assert_patch_failed(self.archive())

    def test_missing_output_directory_prevents_archive(self):
        """上游输出目录不存在时拒绝静默跳过兼容映射。"""
        self.fonts.rmdir()
        self.assert_patch_failed(self.archive())


class WorkflowTests(unittest.TestCase):
    """检查 workflow 使用独立补丁文件及有效的 shell 语法。"""

    def test_checkout_and_preflight(self):
        """从当前提交检出补丁，预检成功之前不进入正式构建。"""
        import yaml

        data = yaml.safe_load((ROOT / ".github/workflows/build-maple.yml").read_text())
        steps = data["jobs"]["build"]["steps"]
        checkout = next(step for step in steps if step["name"] == "📥 Checkout build customizations")
        self.assertEqual(checkout["with"]["sparse-checkout"], "patches")
        self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")
        self.assertEqual(data["env"]["PYTHONPATH"], "${{ github.workspace }}/.maple-custom/patches")
        preflight = next(i for i, step in enumerate(steps) if "Preflight" in step["name"])
        build = next(i for i, step in enumerate(steps) if step["name"] == "🏗️ Build static fonts")
        self.assertLess(preflight, build)
        self.assertIn("PATCH_INSTALLED", steps[preflight]["run"])
        self.assertEqual(steps[preflight]["run"].count("--dry"), 2)

    def test_shell_syntax(self):
        """替换 Actions 表达式后对每个 run 步骤执行 bash 语法检查。"""
        import yaml

        data = yaml.safe_load((ROOT / ".github/workflows/build-maple.yml").read_text())
        for step in data["jobs"]["build"]["steps"]:
            if "run" not in step:
                continue
            with self.subTest(step=step["name"]):
                script = re.sub(r"\$\{\{.*?\}\}", "test-value", step["run"])
                result = subprocess.run(
                    ["bash", "-n"], input=script, capture_output=True, text=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
