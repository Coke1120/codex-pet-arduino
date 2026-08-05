from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "render_mmd_pet_blender.py"
SPEC = importlib.util.spec_from_file_location("render_mmd_pet_blender", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


class _Material:
    def __init__(self, name: str) -> None:
        self.name = name
        self.mmd_material = types.SimpleNamespace(alpha=1.0)


def _mesh(*materials: _Material) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        material_slots=[types.SimpleNamespace(material=material) for material in materials]
    )


class MmdRendererMetadataTests(unittest.TestCase):
    def _args(self, **overrides: object) -> types.SimpleNamespace:
        values: dict[str, object] = {
            "mmd_module": "fake_mmd_tools",
            "provenance_name": "User-provided PMX model",
            "model_page": None,
            "credit": [],
            "rights_note": "Verify model rights before redistributing derived assets.",
        }
        values.update(overrides)
        return types.SimpleNamespace(**values)

    def test_remove_mask_hides_both_materials_and_updates_alpha(self) -> None:
        mask = _Material("マスク")
        mask_eyes = _Material("マスク瞳")
        instances: list[object] = []

        class FakeFnMaterial:
            def __init__(self, material: object) -> None:
                self.material = material
                self.update_alpha = mock.Mock()
                instances.append(self)

        module = types.SimpleNamespace(FnMaterial=FakeFnMaterial)
        with mock.patch.object(RENDERER.importlib, "import_module", return_value=module):
            RENDERER._remove_mask_materials(self._args(), _mesh(mask, mask_eyes))

        self.assertEqual(mask.mmd_material.alpha, 0.0)
        self.assertEqual(mask_eyes.mmd_material.alpha, 0.0)
        self.assertEqual(len(instances), 2)
        for instance in instances:
            instance.update_alpha.assert_called_once_with()

    def test_remove_mask_fails_when_either_required_material_is_missing(self) -> None:
        module = types.SimpleNamespace(FnMaterial=mock.Mock())
        with mock.patch.object(RENDERER.importlib, "import_module", return_value=module):
            with self.assertRaisesRegex(RuntimeError, "マスク瞳"):
                RENDERER._remove_mask_materials(self._args(), _mesh(_Material("マスク")))

    def test_keep_mask_is_opt_in(self) -> None:
        default = RENDERER.parse_args(["--pmx", "model.pmx", "--output-dir", "frames"])
        kept = RENDERER.parse_args(
            ["--pmx", "model.pmx", "--output-dir", "frames", "--keep-mask"]
        )
        self.assertFalse(default.keep_mask)
        self.assertTrue(kept.keep_mask)

    def test_render_padding_rejects_alpha_on_any_edge(self) -> None:
        width = 6
        height = 6
        pixels = [0.0] * (width * height * 4)
        pixels[((3 * width + 3) * 4) + 3] = 1.0
        self.assertTrue(RENDERER._has_safe_padding(pixels, width, height, margin=2))

        pixels[((0 * width + 3) * 4) + 3] = 1.0
        self.assertFalse(RENDERER._has_safe_padding(pixels, width, height, margin=2))

    def test_credits_are_generic_and_do_not_persist_pmx_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            args = self._args(output_dir=output_dir)
            RENDERER._write_credits(args)
            credits = (output_dir / "CREDITS.txt").read_text(encoding="utf-8")

        self.assertIn("Source: User-provided PMX model", credits)
        self.assertNotIn("Source PMX:", credits)
        self.assertNotIn("Sakamata Chloe", credits)
        self.assertNotIn("nicovideo.jp", credits)
        self.assertNotIn("© COVER", credits)

    def test_explicit_provenance_is_written_without_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            args = self._args(
                output_dir=output_dir,
                provenance_name="Sakamata Chloe MMD model",
                model_page="https://3d.nicovideo.jp/works/td84836",
                credit=["© COVER"],
                rights_note="Authorized local prototype.",
            )
            RENDERER._write_credits(args)
            credits = (output_dir / "CREDITS.txt").read_text(encoding="utf-8")

        self.assertIn("Model page: https://3d.nicovideo.jp/works/td84836", credits)
        self.assertIn("Credit: © COVER", credits)
        self.assertNotIn("/Users/", credits)

    def test_absolute_provenance_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = self._args(
                output_dir=Path(directory),
                provenance_name="/Users/example/Downloads/private-model.pmx",
            )
            with self.assertRaisesRegex(ValueError, "descriptive label"):
                RENDERER._write_credits(args)

    def test_external_cmake_status_does_not_echo_asset_path(self) -> None:
        cmake = (ROOT / "esp32-p4" / "main" / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn('message(STATUS "Codex Pet asset source: external override")', cmake)
        self.assertNotIn(
            'message(STATUS "Codex Pet asset source: ${CODEX_PET_ASSET_SOURCE}")', cmake
        )
        self.assertNotIn(
            'message(FATAL_ERROR "CODEX_PET_ASSET_SOURCE does not exist: ', cmake
        )


if __name__ == "__main__":
    unittest.main()
