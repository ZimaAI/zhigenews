"""Exercise deployment transitions in a temporary Linux filesystem, without Docker/SSH.

Run: python3 -m unittest discover -s infra/deploy/tests -v
"""

import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


FAKE_COMMAND = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
command = [Path(sys.argv[0]).name, *sys.argv[1:]]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(command) + "\n")
if os.environ.get("FAIL_ON") and os.environ["FAIL_ON"] in " ".join(command):
    sys.exit(7)
if "printenv" in command:
    print("news.example.com" if command[-1] == "USER_DOMAIN" else "admin.example.com")
if any("mysqldump" in arg for arg in command):
    print("-- synthetic SQL backup")
'''


@unittest.skipUnless(os.name == "posix", "The deployment target uses Linux Bash and flock")
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release = self.root / "releases" / "new"
        self.release.mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] / "deploy.sh", self.release / "deploy.sh")
        for file in (self.root / ".env", self.root / "backend.env", self.release / "release.env"):
            file.write_text("SYNTHETIC=1\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("docker", "curl"):
            command = self.bin / name
            command.write_text(FAKE_COMMAND)
            command.chmod(0o755)
        self.log = self.root / "calls.jsonl"

    def run_deploy(self, fail_on=""):
        result = subprocess.run(
            ["bash", str(self.release / "deploy.sh")],
            env={**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                 "CALL_LOG": str(self.log), "FAIL_ON": fail_on},
            capture_output=True, text=True, timeout=20,
        )
        self.calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result

    def configure_existing(self):
        old = self.root / "releases" / "old"
        old.mkdir()
        (self.root / "current").symlink_to(old)
        (self.root / ".initialized").touch()
        return old

    def test_first_deploy_initializes_before_start_and_promotes_after_https(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [" ".join(call) for call in self.calls]
        init = next(i for i, command in enumerate(commands) if "zhigenews.cli init" in command)
        migrate = next(i for i, command in enumerate(commands) if "alembic upgrade head" in command)
        start = next(i for i, command in enumerate(commands) if "up -d --wait --wait-timeout 240" in command)
        self.assertLess(migrate, init)
        self.assertLess(init, start)
        self.assertEqual(sum(call[0] == "curl" for call in self.calls), 4)
        self.assertTrue((self.root / ".initialized").exists())
        self.assertEqual((self.root / "current").resolve(), self.release)

    def test_update_backs_up_after_drain_and_does_not_reseed(self):
        old = self.configure_existing()
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [" ".join(call) for call in self.calls]
        self.assertFalse(any("zhigenews.cli init" in command for command in commands))
        drain = next(i for i, command in enumerate(commands) if "stop worker" in command)
        backup = next(i for i, command in enumerate(commands) if "mysqldump" in command)
        migrate = next(i for i, command in enumerate(commands) if "alembic upgrade head" in command)
        self.assertLess(drain, backup)
        self.assertLess(backup, migrate)
        sql = next((self.root / "backups").glob("*.sql.gz"))
        self.assertIn("synthetic SQL", gzip.decompress(sql.read_bytes()).decode())
        self.assertEqual((self.root / "previous").resolve(), old)

    def test_pull_failure_keeps_old_services_and_release(self):
        old = self.configure_existing()
        result = self.run_deploy("pull mysql")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("stop" in call for call in self.calls))
        self.assertEqual((self.root / "current").resolve(), old)

    def test_host_override_is_used_for_every_compose_operation(self):
        override = self.root / "compose.override.yaml"
        override.write_text("services: {}\n")
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in self.calls:
            if call[:2] == ["docker", "compose"]:
                self.assertIn(str(override), call)
                self.assertLess(call.index(str(self.release / "compose.yaml")),
                                call.index(str(override)))

    def test_invalid_override_fails_before_stopping_services(self):
        (self.root / "compose.override.yaml").write_text("invalid YAML")
        result = self.run_deploy("config --quiet")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("stop" in call for call in self.calls))

    def test_backup_failure_does_not_migrate(self):
        old = self.configure_existing()
        result = self.run_deploy("mysqldump")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("alembic" in call for call in self.calls))
        self.assertEqual((self.root / "current").resolve(), old)

    def test_migration_failure_does_not_start_new_services(self):
        old = self.configure_existing()
        result = self.run_deploy("alembic upgrade")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("up" in call and "web" in call for call in self.calls))
        self.assertEqual((self.root / "current").resolve(), old)

    def test_https_failure_does_not_mark_release_successful(self):
        old = self.configure_existing()
        result = self.run_deploy("curl")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertFalse((self.root / "previous").exists())


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is required; no daemon needed")
class ComposeConfigurationTests(unittest.TestCase):
    def test_nginx_override_exposes_only_loopback_http(self):
        deploy = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "backend.env").write_text("ADMIN_PASSWORD=synthetic-only\n")
            result = subprocess.run(
                ["docker", "compose", "--env-file", str(deploy / ".env.example"),
                 "-f", str(deploy / "compose.yaml"),
                 "-f", str(deploy / "compose.nginx.yaml"), "config", "--format", "json"],
                env={**os.environ, "DEPLOY_ROOT": directory,
                     "BACKEND_IMAGE": "synthetic-backend:test", "WEB_IMAGE": "synthetic-web:test",
                     "MYSQL_PASSWORD": "synthetic", "MYSQL_ROOT_PASSWORD": "synthetic"},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads(result.stdout)
            services = config["services"]
            self.assertEqual(services["web"]["ports"], [{
                "mode": "ingress", "host_ip": "127.0.0.1", "target": 80,
                "published": "18080", "protocol": "tcp",
            }])
            for name in ["mysql", "redis", "api", "worker", "beat"]:
                self.assertFalse(services[name].get("ports"))
            self.assertEqual(services["api"]["environment"]["COOKIE_SECURE"], "true")
            self.assertIn("/etc/caddy/Caddyfile.nginx", services["web"]["command"])
            network = config["networks"]["default"]["ipam"]["config"]
            self.assertEqual(len(network), 1)
            self.assertEqual(network[0]["gateway"], "172.30.0.1")
            self.assertEqual(services["web"]["environment"]["EDGE_PROXY_CIDRS"], "172.30.0.1/32")


if __name__ == "__main__":
    unittest.main()
