import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "mac" / "install.sh"


class MacInstallerTests(unittest.TestCase):
    def run_installer(
        self,
        runtime: Path,
        launch_agents: Path,
        *extra: str,
        skip_launchctl: bool = True,
        env=None,
    ):
        command = [
            "bash",
            str(INSTALLER),
            "--runtime-dir",
            str(runtime),
            "--launch-agents-dir",
            str(launch_agents),
            "--skip-dependencies",
        ]
        if skip_launchctl:
            command.append("--skip-launchctl")
        command.extend(extra)
        return subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_installer_updates_runtime_and_preserves_existing_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            existing_plist = launch_agents / "com.coke1120.codex-pet.plist"
            with existing_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": "com.coke1120.codex-pet",
                        "ProgramArguments": [
                            "/old/python",
                            "/old/daemon.py",
                            "--port",
                            "/dev/cu.persisted",
                        ],
                    },
                    handle,
                )

            first = self.run_installer(runtime, launch_agents)

            self.assertIn("port: /dev/cu.persisted", first.stdout)
            self.assertEqual(
                (runtime / "codex_pet_daemon.py").read_bytes(),
                (ROOT / "mac" / "codex_pet_daemon.py").read_bytes(),
            )
            self.assertEqual(
                (runtime / "codex_pet_hook.py").read_bytes(),
                (ROOT / "mac" / "codex_pet_hook.py").read_bytes(),
            )
            self.assertEqual(
                (runtime / "codex_pet_usage.py").read_bytes(),
                (ROOT / "mac" / "codex_pet_usage.py").read_bytes(),
            )
            with existing_plist.open("rb") as handle:
                plist = plistlib.load(handle)
            self.assertEqual(plist["ProgramArguments"][-2:], ["--port", "/dev/cu.persisted"])
            self.assertEqual(
                plist["ProgramArguments"][:2],
                [
                    str(runtime / "bin" / "python"),
                    str(runtime / "codex_pet_daemon.py"),
                ],
            )

            (runtime / "codex_pet_daemon.py").write_text("stale\n", encoding="utf-8")
            second = self.run_installer(
                runtime, launch_agents, "--port", "/dev/cu.usbmodem-test"
            )

            self.assertIn("port: /dev/cu.usbmodem-test", second.stdout)
            self.assertEqual(
                (runtime / "codex_pet_daemon.py").read_bytes(),
                (ROOT / "mac" / "codex_pet_daemon.py").read_bytes(),
            )
            with existing_plist.open("rb") as handle:
                updated = plistlib.load(handle)
            self.assertEqual(
                updated["ProgramArguments"][-1], "/dev/cu.usbmodem-test"
            )
            self.assertEqual(list(runtime.glob("*.tmp.*")), [])
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])

    def test_installer_rejects_invalid_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            result = subprocess.run(
                [
                    "bash",
                    str(INSTALLER),
                    "--runtime-dir",
                    str(base / "runtime"),
                    "--launch-agents-dir",
                    str(base / "agents"),
                    "--label",
                    "bad label",
                    "--skip-dependencies",
                    "--skip-launchctl",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid LaunchAgent label", result.stderr)

    def test_launchd_reload_uses_reliable_plist_bootout(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn(
            '"$launchctl_bin" bootout "$service_domain" "$plist_path"', source
        )
        self.assertIn(
            '"$launchctl_bin" bootstrap "$service_domain" "$plist_path"', source
        )
        self.assertNotIn("launchctl kickstart", source)

    def test_installer_migrates_legacy_launch_agent_without_competing_daemons(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            legacy_plist = launch_agents / "org.example.codex-pet.plist"
            with legacy_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": "org.example.codex-pet",
                        "ProgramArguments": [
                            "/old/python",
                            "/old/daemon.py",
                            "--port",
                            "/dev/cu.legacy-port",
                        ],
                    },
                    handle,
                )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n',
                encoding="utf-8",
            )
            fake_launchctl.chmod(0o755)
            environment = dict(os.environ)
            environment.update(
                {
                    "CODEX_PET_PLATFORM_NAME": "Darwin",
                    "CODEX_PET_LAUNCHCTL_BIN": str(fake_launchctl),
                    "CODEX_PET_LAUNCHCTL_LOG": str(launchctl_log),
                    "CODEX_PET_USER_ID": "501",
                }
            )

            result = self.run_installer(
                runtime,
                launch_agents,
                skip_launchctl=False,
                env=environment,
            )

            current_plist = launch_agents / "com.coke1120.codex-pet.plist"
            self.assertFalse(legacy_plist.exists())
            self.assertEqual(list(launch_agents.glob("*.plist")), [current_plist])
            with current_plist.open("rb") as handle:
                installed = plistlib.load(handle)
            self.assertEqual(installed["ProgramArguments"][-1], "/dev/cu.legacy-port")
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertIn(
                "bootout gui/501 {}".format(legacy_plist), launchctl_calls
            )
            self.assertIn(
                "bootout gui/501 {}".format(current_plist), launchctl_calls
            )
            self.assertIn(
                "bootstrap gui/501 {}".format(current_plist), launchctl_calls
            )
            self.assertIn("port: /dev/cu.legacy-port", result.stdout)


if __name__ == "__main__":
    unittest.main()
