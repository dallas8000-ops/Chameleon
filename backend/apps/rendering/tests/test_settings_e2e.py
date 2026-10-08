"""settings_e2e must enforce isolation itself, whatever launcher or environment loads it."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
SCRATCH = (BACKEND.parent / "e2e" / ".runtime").resolve()

PROBE = (
    "import json, django.conf as c, os;"
    "os.environ['DJANGO_SETTINGS_MODULE']='chameleon.settings_e2e';"
    "s=c.settings;"
    "print(json.dumps({'engine': s.DATABASES['default']['ENGINE'], 'name': str(s.DATABASES['default']['NAME']),"
    " 'media': str(s.MEDIA_ROOT), 'key': s.MAGIC_HOUR_API_KEY, 'eager': s.CELERY_TASK_ALWAYS_EAGER}))"
)


def run_probe(**overrides):
    env = {k: v for k, v in os.environ.items() if k not in {
        "CHAMELEON_E2E", "CHAMELEON_E2E_RUNTIME_DIR", "DATABASE_URL", "MEDIA_ROOT", "DJANGO_SETTINGS_MODULE"}}
    env.update(SECRET_KEY="e2e-" + "x" * 40, REDIS_URL="redis://127.0.0.1:1/0", MAGIC_HOUR_API_KEY="")
    env.update({k: v for k, v in overrides.items() if v is not None})
    return subprocess.run([sys.executable, "-c", PROBE], cwd=BACKEND, env=env, capture_output=True, text=True)


class SettingsE2EIsolationTests(unittest.TestCase):
    def test_refuses_without_opt_in(self):
        result = run_probe(CHAMELEON_E2E_RUNTIME_DIR=str(SCRATCH))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHAMELEON_E2E", result.stderr)

    def test_refuses_without_scratch_dir(self):
        result = run_probe(CHAMELEON_E2E="1", DATABASE_URL="sqlite:///x.sqlite3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHAMELEON_E2E_RUNTIME_DIR", result.stderr)

    def test_refuses_scratch_dir_outside_repo_e2e_runtime(self):
        with tempfile.TemporaryDirectory() as other:
            result = run_probe(CHAMELEON_E2E="1", CHAMELEON_E2E_RUNTIME_DIR=other)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("e2e", result.stderr)

    def test_refuses_external_database_url(self):
        result = run_probe(CHAMELEON_E2E="1", CHAMELEON_E2E_RUNTIME_DIR=str(SCRATCH),
                           DATABASE_URL="postgres://user:pw@db.example.com/prod")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL", result.stderr)
        self.assertNotIn("pw@", result.stderr)

    def test_refuses_sqlite_outside_scratch(self):
        result = run_probe(CHAMELEON_E2E="1", CHAMELEON_E2E_RUNTIME_DIR=str(SCRATCH),
                           DATABASE_URL="sqlite:///" + str(BACKEND / "db.sqlite3").replace("\\", "/"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL", result.stderr)

    def test_refuses_media_root_outside_scratch(self):
        result = run_probe(CHAMELEON_E2E="1", CHAMELEON_E2E_RUNTIME_DIR=str(SCRATCH),
                           MEDIA_ROOT=str(BACKEND / "private_media"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MEDIA_ROOT", result.stderr)

    def test_forces_scratch_sqlite_and_media_without_launcher_help(self):
        result = run_probe(CHAMELEON_E2E="1", CHAMELEON_E2E_RUNTIME_DIR=str(SCRATCH))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["engine"].endswith("sqlite3"))
        self.assertTrue(Path(data["name"]).resolve().is_relative_to(SCRATCH))
        self.assertTrue(Path(data["media"]).resolve().is_relative_to(SCRATCH))
        self.assertEqual(data["key"], "")
        self.assertTrue(data["eager"])

