import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "windows" / "install.ps1"


class WindowsInstallerTests(unittest.TestCase):
    def test_shared_daemon_modules_are_copied_to_runtime(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        for module in (
            "codex_pet_daemon.py",
            "codex_pet_hook.py",
            "codex_pet_usage.py",
        ):
            with self.subTest(module=module):
                self.assertIn(
                    'Copy-Item (Join-Path $RepoRoot "mac\\{}") $Runtime -Force'.format(
                        module
                    ),
                    source,
                )


if __name__ == "__main__":
    unittest.main()
