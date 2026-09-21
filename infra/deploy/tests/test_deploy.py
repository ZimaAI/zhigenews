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


if __name__ == "__main__":
    unittest.main()
