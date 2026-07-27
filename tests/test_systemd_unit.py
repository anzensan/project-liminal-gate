from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIT_TEMPLATE = PROJECT_ROOT / "deploy" / "project-liminal-gate.service.in"
INSTALLER = PROJECT_ROOT / "scripts" / "install_systemd_service.sh"
README = PROJECT_ROOT / "README.md"


class SystemdUnitTest(unittest.TestCase):
    def render(self) -> str:
        return (
            UNIT_TEMPLATE.read_text(encoding="utf-8")
            .replace("@SERVICE_USER@", "tester")
            .replace("@SERVICE_GROUP@", "tester")
            .replace("@PROJECT_ROOT@", "/srv/project-liminal-gate")
            .replace("@PYTHON_EXECUTABLE@", "/usr/bin/python3")
            .replace("@PORT@", "8642")
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

    def test_readme_documents_generic_dedicated_server_lifecycle(self) -> None:
        readme = README.read_text(encoding="utf-8")
        section = readme.split(
            "### Run only the server on a separate Linux machine", 1
        )[1].split("### 3. One-command setup", 1)[0]
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
