import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "esp32-p4" / "main"
ABI_MARKER = "// CODEX_PET_GENERATED_ABI: 2"


@unittest.skipUnless(shutil.which("cmake"), "cmake is required")
class GeneratedAssetAbiCMakeTests(unittest.TestCase):
    def _run_cmake(
        self, *, local_source=None, external_source=None, early_expansion=False
    ):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            shutil.copy2(MAIN / "CMakeLists.txt", work / "CMakeLists.txt")
            if local_source is not None:
                (work / "pet_generated.c").write_text(local_source, encoding="utf-8")
            if external_source is not None:
                external = work / "external_generated.c"
                external.write_text(external_source, encoding="utf-8")
            else:
                external = None

            harness = work / "harness.cmake"
            harness.write_text(
                "function(idf_component_register)\nendfunction()\n"
                "function(target_compile_options)\nendfunction()\n"
                "function(idf_component_set_property)\nendfunction()\n"
                "set(COMPONENT_LIB codex_pet_test)\n"
                f'include("{work / "CMakeLists.txt"}")\n'
                "get_cmake_property(all_variables VARIABLES)\n"
                "foreach(variable IN LISTS all_variables)\n"
                "  if(variable MATCHES \"^PET_GENERATED_ASSET_(PREFIX|ABI_MARKER)$\")\n"
                "    message(FATAL_ERROR \"generated source content escaped validation scope\")\n"
                "  endif()\n"
                "endforeach()\n",
                encoding="utf-8",
            )
            command = ["cmake"]
            if early_expansion:
                command.append("-DCMAKE_BUILD_EARLY_EXPANSION=1")
            if external is not None:
                command.append(f"-DCODEX_PET_ASSET_SOURCE={external}")
            command.extend(["-P", str(harness)])
            return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_header_declares_current_generated_asset_abi(self):
        header = (MAIN / "pet_generated.h").read_text(encoding="utf-8")
        self.assertIn("#define CODEX_PET_GENERATED_ABI 2", header)

    def test_rejects_stale_local_generated_source_without_echoing_path(self):
        result = self._run_cmake(local_source="/* stale generated source */\n")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generated asset uses an unsupported ABI", output)
        self.assertIn("tools/convert_codex_pet_p4.py", output)
        self.assertNotIn("pet_generated.c", output)

    def test_rejects_stale_external_generated_source_without_echoing_path(self):
        result = self._run_cmake(external_source="/* stale generated source */\n")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generated asset uses an unsupported ABI", output)
        self.assertNotIn("external_generated.c", output)

    def test_requirements_early_expansion_does_not_validate_local_fallback(self):
        result = self._run_cmake(
            local_source="/* stale generated source */\n", early_expansion=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_accepts_marked_local_generated_source(self):
        result = self._run_cmake(local_source=f"{ABI_MARKER}\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_accepts_marked_external_generated_source(self):
        result = self._run_cmake(external_source=f"{ABI_MARKER}\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_marker_must_be_an_exact_standalone_comment(self):
        result = self._run_cmake(local_source=f"/* {ABI_MARKER} */\n")
        self.assertNotEqual(result.returncode, 0)

    def test_marker_must_be_the_first_line(self):
        result = self._run_cmake(local_source=f"/* preamble */\n{ABI_MARKER}\n")
        self.assertNotEqual(result.returncode, 0)

    def test_arbitrary_generated_c_after_marker_does_not_leak_into_cmake(self):
        source = (
            f"{ABI_MARKER}\n"
            'const char *payload = "quotes; ${CMAKE_CURRENT_LIST_DIR}; [=[text]=]";\n'
            "static const unsigned char bytes[] = {0x00, 0xff};\n"
        )
        result = self._run_cmake(external_source=source)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("Argument not separated", output)


if __name__ == "__main__":
    unittest.main()
