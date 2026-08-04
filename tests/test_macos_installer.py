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
        skip_dependencies: bool = True,
        env=None,
        check: bool = True,
    ):
        command = [
            "bash",
            str(INSTALLER),
            "--runtime-dir",
            str(runtime),
            "--launch-agents-dir",
            str(launch_agents),
        ]
        if skip_dependencies:
            command.append("--skip-dependencies")
        if skip_launchctl:
            command.append("--skip-launchctl")
        command.extend(extra)
        return subprocess.run(
            command,
            cwd=ROOT,
            check=check,
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

    def test_pip_failure_does_not_mutate_existing_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            (runtime / "bin").mkdir(parents=True)
            runtime_python = runtime / "bin" / "python"
            runtime_python.write_text(
                "#!/usr/bin/env bash\n"
                'if [[ "$1" == "-m" && "$2" == "pip" && "$3" == "install" ]]; then\n'
                "  exit 17\n"
                "fi\n"
                'exec /usr/bin/env python3 "$@"\n',
                encoding="utf-8",
            )
            runtime_python.chmod(0o755)
            original_daemon = runtime / "codex_pet_daemon.py"
            original_daemon.write_text("original runtime\n", encoding="utf-8")
            original_marker = runtime / "runtime.marker"
            original_marker.write_text("keep me\n", encoding="utf-8")

            result = self.run_installer(
                runtime,
                launch_agents,
                skip_dependencies=False,
                check=False,
            )

            self.assertEqual(result.returncode, 17)
            self.assertEqual(
                original_daemon.read_text(encoding="utf-8"),
                "original runtime\n",
            )
            self.assertEqual(original_marker.read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual(
                (runtime / "bin" / "python").read_text(encoding="utf-8").splitlines()[0],
                "#!/usr/bin/env bash",
            )
            self.assertEqual(list(runtime.parent.glob(".codex-pet-runtime.*")), [])
            self.assertEqual(list(launch_agents.glob("*.plist")), [])

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

    def test_installer_rejects_root_runtime_before_mutation(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("os.sep", source)
        self.assertLess(
            source.index("normalized_runtime_dir=$("),
            source.index('mkdir -p "$runtime_parent"'),
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            launch_agents = base / "LaunchAgents"
            result = self.run_installer(
                Path("/"),
                launch_agents,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Unsafe runtime directory", result.stderr)
            self.assertFalse(launch_agents.exists())

    def test_installer_rejects_workspace_ancestor_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            launch_agents = base / "LaunchAgents"
            result = self.run_installer(
                base,
                launch_agents,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Unsafe runtime directory", result.stderr)
            self.assertFalse(launch_agents.exists())
            self.assertEqual(list(base.glob(".codex-pet-runtime.*")), [])

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
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 1; fi\n',
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

    def test_custom_label_unloads_and_removes_default_and_legacy_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            default_plist = launch_agents / "com.coke1120.codex-pet.plist"
            legacy_plist = launch_agents / "org.example.codex-pet.plist"
            for path, label in (
                (default_plist, "com.coke1120.codex-pet"),
                (legacy_plist, "org.example.codex-pet"),
            ):
                with path.open("wb") as handle:
                    plistlib.dump(
                        {"Label": label, "ProgramArguments": ["python", "daemon"]},
                        handle,
                    )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 1; fi\n',
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

            self.run_installer(
                runtime,
                launch_agents,
                "--label",
                "com.example.custom-pet",
                skip_launchctl=False,
                env=environment,
            )

            custom_plist = launch_agents / "com.example.custom-pet.plist"
            self.assertEqual(list(launch_agents.glob("*.plist")), [custom_plist])
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertIn("bootout gui/501 {}".format(default_plist), launchctl_calls)
            self.assertIn("bootout gui/501 {}".format(legacy_plist), launchctl_calls)
            self.assertIn("bootstrap gui/501 {}".format(custom_plist), launchctl_calls)

    def test_custom_label_change_unloads_prior_custom_agent_and_preserves_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "Codex Pet" / "runtime"
            launch_agents = base / "Launch Agents"
            launch_agents.mkdir(parents=True)
            old_label = "com.example.custom-a"
            new_label = "com.example.custom-b"
            old_plist = launch_agents / (old_label + ".plist")
            with old_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": old_label,
                        "ProgramArguments": [
                            str(runtime / "bin" / "python"),
                            str(runtime / "codex_pet_daemon.py"),
                            "--port",
                            "/dev/cu.custom-port",
                        ],
                    },
                    handle,
                )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 1; fi\n',
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
                "--label",
                new_label,
                skip_launchctl=False,
                env=environment,
            )

            new_plist = launch_agents / (new_label + ".plist")
            self.assertFalse(old_plist.exists())
            self.assertEqual(list(launch_agents.glob("*.plist")), [new_plist])
            with new_plist.open("rb") as handle:
                installed = plistlib.load(handle)
            self.assertEqual(installed["ProgramArguments"][-1], "/dev/cu.custom-port")
            self.assertIn("port: /dev/cu.custom-port", result.stdout)
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertIn("bootout gui/501 {}".format(old_plist), launchctl_calls)
            self.assertIn("bootstrap gui/501 {}".format(new_plist), launchctl_calls)

    def test_custom_label_change_across_runtime_dirs_uses_managed_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime_a = base / "Codex Pet A" / "runtime"
            runtime_b = base / "Codex Pet B" / "runtime"
            launch_agents = base / "Launch Agents"
            old_label = "com.example.custom-a"
            new_label = "com.example.custom-b"

            self.run_installer(
                runtime_a,
                launch_agents,
                "--label",
                old_label,
                "--port",
                "/dev/cu.relocated",
            )
            old_plist = launch_agents / (old_label + ".plist")
            with old_plist.open("rb") as handle:
                old_payload = plistlib.load(handle)
            self.assertEqual(
                old_payload["CodexPetManaged"], "com.coke1120.codex-pet"
            )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 1; fi\n',
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
                runtime_b,
                launch_agents,
                "--label",
                new_label,
                skip_launchctl=False,
                env=environment,
            )

            new_plist = launch_agents / (new_label + ".plist")
            self.assertFalse(old_plist.exists())
            self.assertTrue(new_plist.exists())
            with new_plist.open("rb") as handle:
                installed = plistlib.load(handle)
            self.assertEqual(
                installed["ProgramArguments"][:2],
                [
                    str(runtime_b / "bin" / "python"),
                    str(runtime_b / "codex_pet_daemon.py"),
                ],
            )
            self.assertEqual(installed["ProgramArguments"][-1], "/dev/cu.relocated")
            self.assertIn("port: /dev/cu.relocated", result.stdout)
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertIn("bootout gui/501 {}".format(old_plist), launchctl_calls)
            self.assertIn("bootstrap gui/501 {}".format(new_plist), launchctl_calls)

    def test_skip_launchctl_rejects_competing_custom_agent_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            old_label = "com.example.skip-old"
            new_label = "com.example.skip-new"

            self.run_installer(
                runtime,
                launch_agents,
                "--label",
                old_label,
                "--port",
                "/dev/cu.skip",
            )
            old_plist = launch_agents / (old_label + ".plist")
            old_bytes = old_plist.read_bytes()

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                new_label,
                check=False,
            )

            new_plist = launch_agents / (new_label + ".plist")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(old_plist.read_bytes(), old_bytes)
            self.assertFalse(new_plist.exists())
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])
            self.assertIn("--skip-launchctl", result.stderr)

    def test_skip_launchctl_plist_move_failure_restores_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            (runtime / "bin").mkdir(parents=True)
            runtime_python = runtime / "bin" / "python"
            runtime_python.write_text(
                "#!/usr/bin/env bash\n"
                'exec /usr/bin/env python3 "$@"\n',
                encoding="utf-8",
            )
            runtime_python.chmod(0o755)
            runtime_daemon = runtime / "codex_pet_daemon.py"
            runtime_daemon.write_text("original runtime\n", encoding="utf-8")
            runtime_marker = runtime / "runtime.marker"
            runtime_marker.write_text("keep me\n", encoding="utf-8")

            mv_dir = base / "bin"
            mv_dir.mkdir()
            mv_shim = mv_dir / "mv"
            mv_shim.write_text(
                "#!/usr/bin/env bash\n"
                'for arg in "$@"; do\n'
                '  case "$arg" in\n'
                '    *.plist.tmp.*) exit 1 ;;\n'
                '  esac\n'
                'done\n'
                'exec /bin/mv "$@"\n',
                encoding="utf-8",
            )
            mv_shim.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = str(mv_dir) + ":" + environment["PATH"]

            result = self.run_installer(
                runtime,
                launch_agents,
                skip_launchctl=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(
                runtime_daemon.read_text(encoding="utf-8"),
                "original runtime\n",
            )
            self.assertEqual(runtime_marker.read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual(list(launch_agents.glob("*.plist")), [])
            self.assertEqual(list(runtime.parent.glob(".codex-pet-runtime.*")), [])

    def test_failed_bootout_preserves_loaded_custom_agent_and_skips_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            old_label = "com.example.loaded-old"
            new_label = "com.example.loaded-new"
            old_plist = launch_agents / (old_label + ".plist")
            with old_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": old_label,
                        "ProgramArguments": [
                            str(runtime / "bin" / "python"),
                            str(runtime / "codex_pet_daemon.py"),
                            "--port",
                            "/dev/cu.loaded",
                        ],
                    },
                    handle,
                )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then\n'
                '  if [[ "$2" == "$CODEX_PET_LOADED_TARGET" ]]; then exit 0; fi\n'
                '  exit 1\n'
                'fi\n'
                'if [[ "$1" == "bootout" && "$3" == "$CODEX_PET_FAILED_PLIST" ]]; then exit 1; fi\n',
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
                    "CODEX_PET_LOADED_TARGET": "gui/501/" + old_label,
                    "CODEX_PET_FAILED_PLIST": str(old_plist),
                }
            )

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                new_label,
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue(old_plist.exists())
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertGreaterEqual(
                launchctl_calls.count("bootout gui/501 {}".format(old_plist)), 2
            )
            self.assertNotIn(" bootstrap ", launchctl_calls)
            self.assertIn("Unable to unload loaded Codex Pet", result.stderr)

    def test_failed_selected_bootout_skips_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            label = "com.example.selected-loaded"
            selected_plist = launch_agents / (label + ".plist")
            with selected_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": label,
                        "ProgramArguments": [
                            str(runtime / "bin" / "python"),
                            str(runtime / "codex_pet_daemon.py"),
                            "--port",
                            "/dev/cu.selected",
                        ],
                    },
                    handle,
                )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 0; fi\n'
                'if [[ "$1" == "bootout" ]]; then exit 1; fi\n',
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
                "--label",
                label,
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue(selected_plist.exists())
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertGreaterEqual(
                launchctl_calls.count("bootout gui/501 {}".format(selected_plist)), 2
            )
            self.assertNotIn(" bootstrap ", launchctl_calls)
            self.assertIn("Unable to unload loaded Codex Pet", result.stderr)

    def test_failed_same_label_bootout_preserves_original_plist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            label = "com.example.same-loaded"

            self.run_installer(
                runtime,
                launch_agents,
                "--label",
                label,
                "--port",
                "/dev/cu.same-loaded",
            )
            selected_plist = launch_agents / (label + ".plist")
            original_bytes = selected_plist.read_bytes()
            runtime_daemon = runtime / "codex_pet_daemon.py"
            runtime_daemon.write_text("original runtime\n", encoding="utf-8")

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 0; fi\n'
                'if [[ "$1" == "bootout" ]]; then exit 1; fi\n',
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
                "--label",
                label,
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(selected_plist.read_bytes(), original_bytes)
            self.assertEqual(list(launch_agents.glob("*.plist")), [selected_plist])
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])
            self.assertEqual(
                runtime_daemon.read_text(encoding="utf-8"),
                "original runtime\n",
            )
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertNotIn(" bootstrap ", launchctl_calls)
            self.assertIn("Unable to unload loaded Codex Pet", result.stderr)

    def test_failed_bootstrap_restores_original_plist_and_loaded_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            label = "com.example.bootstrap-failed"

            self.run_installer(
                runtime,
                launch_agents,
                "--label",
                label,
                "--port",
                "/dev/cu.original",
            )
            selected_plist = launch_agents / (label + ".plist")
            with selected_plist.open("rb") as handle:
                original_payload = plistlib.load(handle)
            original_payload["Label"] = "com.example.original-service"
            with selected_plist.open("wb") as handle:
                plistlib.dump(original_payload, handle)
            original_bytes = selected_plist.read_bytes()
            runtime_sentinel = runtime / "runtime-sentinel.txt"
            runtime_sentinel.write_text("keep-old-runtime\n", encoding="utf-8")
            runtime_files = {}
            for runtime_name in (
                "codex_pet_daemon.py",
                "codex_pet_hook.py",
                "codex_pet_usage.py",
                "requirements.txt",
            ):
                runtime_file = runtime / runtime_name
                runtime_file.write_bytes((b"old-runtime-" + runtime_name.encode("utf-8")))
                runtime_files[runtime_name] = runtime_file.read_bytes()
            state_file = base / "state"
            state_file.write_text("loaded\n", encoding="utf-8")
            bootstrap_count = base / "bootstrap-count"
            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then\n'
                '  if [[ "$(cat "$CODEX_PET_STATE_FILE" 2>/dev/null)" == "loaded" ]]; then exit 0; fi\n'
                '  exit 1\n'
                'fi\n'
                'if [[ "$1" == "bootout" ]]; then printf "notloaded\\n" > "$CODEX_PET_STATE_FILE"; exit 0; fi\n'
                'if [[ "$1" == "bootstrap" ]]; then\n'
                '  count=0\n'
                '  if [[ -f "$CODEX_PET_BOOTSTRAP_COUNT" ]]; then count=$(cat "$CODEX_PET_BOOTSTRAP_COUNT"); fi\n'
                '  count=$((count + 1))\n'
                '  printf "%s\\n" "$count" > "$CODEX_PET_BOOTSTRAP_COUNT"\n'
                '  if [[ $count -lt 3 ]]; then exit 1; fi\n'
                '  printf "loaded\\n" > "$CODEX_PET_STATE_FILE"\n'
                '  exit 0\n'
                'fi\n',
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
                    "CODEX_PET_STATE_FILE": str(state_file),
                    "CODEX_PET_BOOTSTRAP_COUNT": str(bootstrap_count),
                }
            )

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                label,
                "--port",
                "/dev/cu.replacement",
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(selected_plist.read_bytes(), original_bytes)
            self.assertEqual(runtime_sentinel.read_text(encoding="utf-8"), "keep-old-runtime\n")
            for runtime_name, expected_bytes in runtime_files.items():
                self.assertEqual((runtime / runtime_name).read_bytes(), expected_bytes)
            self.assertEqual(list(launch_agents.glob("*.plist")), [selected_plist])
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])
            self.assertEqual(state_file.read_text(encoding="utf-8").strip(), "loaded")
            self.assertEqual(bootstrap_count.read_text(encoding="utf-8").strip(), "3")
            self.assertNotIn("rollback incomplete", result.stderr)
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertIn("print gui/501/com.example.original-service", launchctl_calls)
            self.assertIn("print gui/501/" + label, launchctl_calls)

    def test_failed_first_bootstrap_removes_new_plist_and_loaded_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            label = "com.example.first-bootstrap-failed"
            state_file = base / "state"
            state_file.write_text("notloaded\n", encoding="utf-8")
            bootstrap_count = base / "bootstrap-count"
            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then\n'
                '  if [[ "$(cat "$CODEX_PET_STATE_FILE")" == "loaded" ]]; then exit 0; fi\n'
                '  exit 1\n'
                'fi\n'
                'if [[ "$1" == "bootout" ]]; then printf "notloaded\\n" > "$CODEX_PET_STATE_FILE"; exit 0; fi\n'
                'if [[ "$1" == "bootstrap" ]]; then\n'
                '  count=0\n'
                '  if [[ -f "$CODEX_PET_BOOTSTRAP_COUNT" ]]; then count=$(cat "$CODEX_PET_BOOTSTRAP_COUNT"); fi\n'
                '  count=$((count + 1))\n'
                '  printf "%s\\n" "$count" > "$CODEX_PET_BOOTSTRAP_COUNT"\n'
                '  exit 1\n'
                'fi\n',
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
                    "CODEX_PET_STATE_FILE": str(state_file),
                    "CODEX_PET_BOOTSTRAP_COUNT": str(bootstrap_count),
                }
            )

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                label,
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            selected_plist = launch_agents / (label + ".plist")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(selected_plist.exists())
            self.assertFalse(runtime.exists())
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])
            self.assertEqual(list(launch_agents.glob(".codex-pet-transaction.*")), [])
            self.assertEqual(state_file.read_text(encoding="utf-8").strip(), "notloaded")
            self.assertEqual(bootstrap_count.read_text(encoding="utf-8").strip(), "2")
            self.assertNotIn("rollback incomplete", result.stderr)

    def test_partial_multi_agent_unload_rolls_back_prior_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            first_label = "com.example.partial-a"
            second_label = "com.example.partial-b"
            first_plist = launch_agents / (first_label + ".plist")
            second_plist = launch_agents / (second_label + ".plist")
            for path, label, port in (
                (first_plist, first_label, "/dev/cu.partial-a"),
                (second_plist, second_label, "/dev/cu.partial-b"),
            ):
                with path.open("wb") as handle:
                    plistlib.dump(
                        {
                            "Label": label,
                            "ProgramArguments": [
                                str(runtime / "bin" / "python"),
                                str(runtime / "codex_pet_daemon.py"),
                                "--port",
                                port,
                            ],
                        },
                        handle,
                    )
            first_bytes = first_plist.read_bytes()
            second_bytes = second_plist.read_bytes()
            first_state = base / "first-state"
            second_state = base / "second-state"
            selected_state = base / "selected-state"
            first_state.write_text("loaded\n", encoding="utf-8")
            second_state.write_text("loaded\n", encoding="utf-8")
            selected_state.write_text("notloaded\n", encoding="utf-8")
            second_bootouts = base / "second-bootouts"
            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then\n'
                '  case "$2" in\n'
                '    gui/501/com.example.partial-a) state_file="$CODEX_PET_FIRST_STATE" ;;\n'
                '    gui/501/com.example.partial-b) state_file="$CODEX_PET_SECOND_STATE" ;;\n'
                '    *) state_file="$CODEX_PET_SELECTED_STATE" ;;\n'
                '  esac\n'
                '  if [[ "$(cat "$state_file")" == "loaded" ]]; then exit 0; fi\n'
                '  exit 1\n'
                'fi\n'
                'if [[ "$1" == "bootout" ]]; then\n'
                '  if [[ "$3" == "$CODEX_PET_FIRST_PLIST" ]]; then printf "notloaded\\n" > "$CODEX_PET_FIRST_STATE"; exit 0; fi\n'
                '  if [[ "$3" == "$CODEX_PET_SECOND_PLIST" ]]; then\n'
                '    count=0\n'
                '    if [[ -f "$CODEX_PET_SECOND_BOOTOUTS" ]]; then count=$(cat "$CODEX_PET_SECOND_BOOTOUTS"); fi\n'
                '    count=$((count + 1))\n'
                '    printf "%s\\n" "$count" > "$CODEX_PET_SECOND_BOOTOUTS"\n'
                '    if [[ $count -lt 3 ]]; then exit 1; fi\n'
                '    printf "notloaded\\n" > "$CODEX_PET_SECOND_STATE"\n'
                '    exit 0\n'
                '  fi\n'
                '  printf "notloaded\\n" > "$CODEX_PET_SELECTED_STATE"\n'
                '  exit 0\n'
                'fi\n'
                'if [[ "$1" == "bootstrap" ]]; then\n'
                '  if [[ "$3" == "$CODEX_PET_FIRST_PLIST" ]]; then printf "loaded\\n" > "$CODEX_PET_FIRST_STATE"; exit 0; fi\n'
                '  if [[ "$3" == "$CODEX_PET_SECOND_PLIST" ]]; then printf "loaded\\n" > "$CODEX_PET_SECOND_STATE"; exit 0; fi\n'
                'fi\n',
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
                    "CODEX_PET_FIRST_STATE": str(first_state),
                    "CODEX_PET_SECOND_STATE": str(second_state),
                    "CODEX_PET_SELECTED_STATE": str(selected_state),
                    "CODEX_PET_FIRST_PLIST": str(first_plist),
                    "CODEX_PET_SECOND_PLIST": str(second_plist),
                    "CODEX_PET_SECOND_BOOTOUTS": str(second_bootouts),
                }
            )

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                "com.example.partial-selected",
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(first_plist.read_bytes(), first_bytes)
            self.assertEqual(second_plist.read_bytes(), second_bytes)
            self.assertFalse(
                (launch_agents / "com.example.partial-selected.plist").exists()
            )
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])
            self.assertEqual(first_state.read_text(encoding="utf-8").strip(), "loaded")
            self.assertEqual(second_state.read_text(encoding="utf-8").strip(), "loaded")
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertIn("bootstrap gui/501 {}".format(first_plist), launchctl_calls)
            self.assertIn("bootstrap gui/501 {}".format(second_plist), launchctl_calls)
            self.assertNotIn("bootstrap gui/501 {}".format(launch_agents / "com.example.partial-selected.plist"), launchctl_calls)

    def test_skip_launchctl_plist_failure_restores_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            label = "com.example.skip-plist-failure"
            self.run_installer(runtime, launch_agents, "--label", label)
            sentinel = runtime / "runtime-sentinel.txt"
            sentinel.write_text("original-runtime\n", encoding="utf-8")
            selected_plist = launch_agents / (label + ".plist")
            selected_plist.unlink()
            selected_plist.mkdir()
            selected_plist.chmod(0o555)

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                label,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "original-runtime\n")
            self.assertTrue(selected_plist.is_dir())
            self.assertEqual(list(launch_agents.glob("*.tmp.*")), [])
            self.assertIn("plist rollback incomplete", result.stderr)

    def test_failed_unload_leaves_live_runtime_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            old_label = "com.example.runtime-old"
            new_label = "com.example.runtime-new"
            self.run_installer(
                runtime,
                launch_agents,
                "--label",
                old_label,
                "--port",
                "/dev/cu.runtime",
            )
            sentinel = runtime / "runtime-sentinel.txt"
            sentinel.write_text("keep-live-runtime\n", encoding="utf-8")
            old_plist = launch_agents / (old_label + ".plist")
            old_plist_bytes = old_plist.read_bytes()
            state_file = base / "state"
            state_file.write_text("loaded\n", encoding="utf-8")
            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then\n'
                '  if [[ "$(cat "$CODEX_PET_STATE_FILE")" == "loaded" ]]; then exit 0; fi\n'
                '  exit 1\n'
                'fi\n'
                'if [[ "$1" == "bootout" ]]; then exit 1; fi\n',
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
                    "CODEX_PET_STATE_FILE": str(state_file),
                }
            )

            result = self.run_installer(
                runtime,
                launch_agents,
                "--label",
                new_label,
                skip_launchctl=False,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep-live-runtime\n")
            self.assertEqual(old_plist.read_bytes(), old_plist_bytes)
            self.assertFalse((launch_agents / (new_label + ".plist")).exists())

    def test_custom_label_preserves_unrelated_and_malformed_plists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            unrelated_plist = launch_agents / "com.example.unrelated.plist"
            with unrelated_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": "com.example.unrelated",
                        "ProgramArguments": ["/other/python", "/other/daemon"],
                    },
                    handle,
                )
            malformed_plist = launch_agents / "com.example.malformed.plist"
            malformed_plist.write_text("not a plist\n", encoding="utf-8")
            lookalike_plist = launch_agents / "com.example.lookalike.plist"
            lookalike_runtime = base / "Other Runtime" / "runtime"
            with lookalike_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "Label": "com.example.lookalike",
                        "ProgramArguments": [
                            str(lookalike_runtime / "bin" / "python"),
                            str(lookalike_runtime / "codex_pet_daemon.py"),
                            "--port",
                            "/dev/cu.lookalike",
                        ],
                    },
                    handle,
                )

            launchctl_log = base / "launchctl.log"
            fake_launchctl = base / "launchctl"
            fake_launchctl.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$CODEX_PET_LAUNCHCTL_LOG"\n'
                'if [[ "$1" == "print" ]]; then exit 1; fi\n',
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

            self.run_installer(
                runtime,
                launch_agents,
                "--label",
                "com.example.custom",
                skip_launchctl=False,
                env=environment,
            )

            self.assertTrue(unrelated_plist.exists())
            self.assertTrue(malformed_plist.exists())
            self.assertTrue(lookalike_plist.exists())
            launchctl_calls = launchctl_log.read_text(encoding="utf-8")
            self.assertNotIn(str(unrelated_plist), launchctl_calls)
            self.assertNotIn(str(malformed_plist), launchctl_calls)
            self.assertNotIn(str(lookalike_plist), launchctl_calls)

    def test_malformed_existing_plist_is_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "CodexPet" / "runtime"
            launch_agents = base / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            plist_path = launch_agents / "com.coke1120.codex-pet.plist"
            with plist_path.open("wb") as handle:
                plistlib.dump([], handle)

            result = self.run_installer(
                runtime, launch_agents, "--port", "/dev/cu.fallback"
            )

            self.assertIn("port: /dev/cu.fallback", result.stdout)
            with plist_path.open("rb") as handle:
                installed = plistlib.load(handle)
            self.assertEqual(installed["ProgramArguments"][-1], "/dev/cu.fallback")


if __name__ == "__main__":
    unittest.main()
