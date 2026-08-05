from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIT_TEMPLATE = PROJECT_ROOT / "deploy" / "project-liminal-gate.service.in"
INSTALLER = PROJECT_ROOT / "scripts" / "install_systemd_service.sh"
DEDICATED_SERVER_DOC = PROJECT_ROOT / "docs" / "dedicated-server.md"


class SystemdUnitTest(unittest.TestCase):
    def render(self, server_flags: str = "") -> str:
        return (
            UNIT_TEMPLATE.read_text(encoding="utf-8")
            .replace("@SERVICE_USER@", "tester")
            .replace("@SERVICE_GROUP@", "tester")
            .replace("@PROJECT_ROOT@", "/srv/project-liminal-gate")
            .replace("@PYTHON_EXECUTABLE@", "/usr/bin/python3")
            .replace("@PORT@", "8642")
            .replace("@SERVER_FLAGS@", server_flags)
        )

    def test_runs_server_only_launcher_as_unprivileged_user(self) -> None:
        source = self.render()
        self.assertIn("User=tester", source)
        self.assertIn("Group=tester", source)
        self.assertIn("WorkingDirectory=/srv/project-liminal-gate", source)
        self.assertIn(
            "ExecStart=/usr/bin/python3 -m liminal_gate.server_setup --port 8642",
            source,
        )
        self.assertNotIn("tester_setup", source)
        self.assertNotIn("--apk", source)
        self.assertNotIn("@SERVICE_USER@", source)
        self.assertNotIn("@PROJECT_ROOT@", source)
        self.assertNotIn("@PYTHON_EXECUTABLE@", source)
        self.assertNotIn("@SERVER_FLAGS@", source)

    def test_the_installer_can_restore_the_stamina_meter(self) -> None:
        """The unit is a systemd host's only chance to pass a launcher flag.

        The meter is off by default, so an operator who wants it back has
        nowhere to say so but the installer -- and the flag has to survive into
        `ExecStart` rather than being accepted and dropped.
        """
        self.assertIn(
            "ExecStart=/usr/bin/python3 -m liminal_gate.server_setup --port 8642 --enable-stamina",
            self.render(" --enable-stamina"),
        )
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("--enable-stamina", source)
        self.assertIn("unknown option:", source)

    def test_the_installer_accepts_every_launcher_flag_the_docs_advertise(self) -> None:
        """A documented systemd flag has to be one the installer really takes.

        `--original-mail-shape` is opt-in and off by default, so a systemd host
        has nowhere to ask for it but here.  The installer parses an allowlist
        and rejects anything outside it, so a flag documented for this launcher
        but missing from that list is refused at install time rather than
        served -- which is exactly what happened when the flag was added to
        `server_setup` and the docs but not to this script.
        """
        for flag in ("--enable-stamina", "--original-mail-shape"):
            with self.subTest(flag=flag):
                self.assertIn(
                    "ExecStart=/usr/bin/python3 -m liminal_gate.server_setup "
                    f"--port 8642 {flag}",
                    self.render(f" {flag}"),
                )
                # The allowlist arm, not merely a mention in a comment or in
                # the rejection message that names the accepted flags.
                self.assertRegex(
                    INSTALLER.read_text(encoding="utf-8"),
                    rf"(?m)^\s*(--\S+\|)*{flag}(\|--\S+)*\)\s*$",
                )

    def test_launcher_flags_accumulate_rather_than_replace(self) -> None:
        """Asking for two flags must not silently drop the first one."""
        self.assertIn(
            "ExecStart=/usr/bin/python3 -m liminal_gate.server_setup "
            "--port 8642 --enable-stamina --original-mail-shape",
            self.render(" --enable-stamina --original-mail-shape"),
        )
        self.assertIn('server_flags+=" $argument"', INSTALLER.read_text(encoding="utf-8"))

    def test_restarts_and_starts_at_normal_boot(self) -> None:
        source = self.render()
        self.assertIn("Restart=always", source)
        self.assertIn("After=network-online.target", source)
        self.assertNotIn("tailscaled.service", source)
        self.assertIn("WantedBy=multi-user.target", source)

    def test_only_user_data_is_writable(self) -> None:
        source = self.render()
        self.assertIn("ProtectSystem=strict", source)
        self.assertIn("ProtectHome=read-only", source)
        self.assertIn(
            "ReadWritePaths=/srv/project-liminal-gate/user-data",
            source,
        )
        self.assertIn("NoNewPrivileges=true", source)
        self.assertIn("CapabilityBoundingSet=", source)

    def test_installer_renders_and_enables_the_unit(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('temporary_directory="$(mktemp -d)"', source)
        self.assertIn(
            'rendered_unit="$temporary_directory/project-liminal-gate.service"',
            source,
        )
        self.assertIn("systemd-analyze verify", source)
        self.assertIn('python_executable="$(command -v python3)"', source)
        self.assertIn("the checkout path cannot contain whitespace", source)
        self.assertIn('mkdir -p -- "$project_root/user-data"', source)
        self.assertIn("/etc/systemd/system/project-liminal-gate.service", source)
        self.assertIn("systemctl enable project-liminal-gate.service", source)
        self.assertIn("systemctl restart project-liminal-gate.service", source)
        self.assertIn("run this installer as the non-root service user", source)

    def test_docs_document_generic_dedicated_server_lifecycle(self) -> None:
        section = DEDICATED_SERVER_DOC.read_text(encoding="utf-8")
        for expected in (
            "server_setup --port 8642 --prepare-only",
            "tester_setup",
            "install_systemd_service.sh 8642",
            "systemctl status project-liminal-gate.service",
            "systemctl restart project-liminal-gate.service",
            "systemctl disable --now project-liminal-gate.service",
            "Tailscale subnet",
        ):
            self.assertIn(expected, section)
        for machine_specific_example in ("/Users/", "/home/", "ssh "):
            self.assertNotIn(machine_specific_example, section)


if __name__ == "__main__":
    unittest.main()
