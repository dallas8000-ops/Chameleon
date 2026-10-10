"""settings_integration must reject anything except the owned local verification stack."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
SCRATCH = (BACKEND.parent / "e2e" / ".runtime-integration").resolve()
DB_URL = "postgresql://postgres@127.0.0.1:55449/chameleon_integration"
REDIS_URL = "redis://127.0.0.1:56379/15"
BROKER_URL = "redis://127.0.0.1:56379/14"

PROBE = (
    "import json, django.conf as c, os;"
    "os.environ['DJANGO_SETTINGS_MODULE']='chameleon.settings_integration';"
    "s=c.settings;"
    "print(json.dumps({'engine': s.DATABASES['default']['ENGINE'], 'name': s.DATABASES['default']['NAME'],"
    " 'host': s.DATABASES['default']['HOST'], 'port': str(s.DATABASES['default']['PORT']),"
    " 'media': str(s.MEDIA_ROOT)}))"
)


def run_probe(**overrides):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "CHAMELEON_INTEGRATION",
            "CHAMELEON_INTEGRATION_RUNTIME_DIR",
            "CHAMELEON_INTEGRATION_POSTGRES_PORT",
            "CHAMELEON_INTEGRATION_REDIS_PORT",
            "DATABASE_URL",
            "REDIS_URL",
            "CELERY_BROKER_URL",
            "MEDIA_ROOT",
            "DJANGO_SETTINGS_MODULE",
        }
    }
    env.update(
        SECRET_KEY="integration-" + "x" * 40,
        DEBUG="1",
        DATABASE_URL=DB_URL,
        REDIS_URL=REDIS_URL,
        CELERY_BROKER_URL=BROKER_URL,
    )
    env.update({k: v for k, v in overrides.items() if v is not None})
    return subprocess.run([sys.executable, "-c", PROBE], cwd=BACKEND, env=env, capture_output=True, text=True)


class SettingsIntegrationIsolationTests(unittest.TestCase):
    def test_refuses_without_opt_in(self):
        result = run_probe(
            CHAMELEON_INTEGRATION_RUNTIME_DIR=str(SCRATCH),
            CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
            CHAMELEON_INTEGRATION_REDIS_PORT="56379",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHAMELEON_INTEGRATION", result.stderr)

    def test_refuses_without_runtime_dir(self):
        result = run_probe(
            CHAMELEON_INTEGRATION="1",
            CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
            CHAMELEON_INTEGRATION_REDIS_PORT="56379",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHAMELEON_INTEGRATION_RUNTIME_DIR", result.stderr)

    def test_refuses_runtime_dir_outside_repo_scratch(self):
        with tempfile.TemporaryDirectory() as other:
            result = run_probe(
                CHAMELEON_INTEGRATION="1",
                CHAMELEON_INTEGRATION_RUNTIME_DIR=other,
                CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
                CHAMELEON_INTEGRATION_REDIS_PORT="56379",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime-integration", result.stderr)

    def test_refuses_default_ports(self):
        result = run_probe(
            CHAMELEON_INTEGRATION="1",
            CHAMELEON_INTEGRATION_RUNTIME_DIR=str(SCRATCH),
            CHAMELEON_INTEGRATION_POSTGRES_PORT="5432",
            CHAMELEON_INTEGRATION_REDIS_PORT="6379",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-default local port", result.stderr)

    def test_refuses_external_database_url(self):
        result = run_probe(
            CHAMELEON_INTEGRATION="1",
            CHAMELEON_INTEGRATION_RUNTIME_DIR=str(SCRATCH),
            CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
            CHAMELEON_INTEGRATION_REDIS_PORT="56379",
            DATABASE_URL="******db.example.com/prod",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL", result.stderr)
        self.assertNotIn("pw@", result.stderr)

    def test_refuses_wrong_redis_databases(self):
        result = run_probe(
            CHAMELEON_INTEGRATION="1",
            CHAMELEON_INTEGRATION_RUNTIME_DIR=str(SCRATCH),
            CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
            CHAMELEON_INTEGRATION_REDIS_PORT="56379",
            REDIS_URL="redis://127.0.0.1:56379/0",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REDIS_URL", result.stderr)

    def test_refuses_media_root_outside_scratch(self):
        result = run_probe(
            CHAMELEON_INTEGRATION="1",
            CHAMELEON_INTEGRATION_RUNTIME_DIR=str(SCRATCH),
            CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
            CHAMELEON_INTEGRATION_REDIS_PORT="56379",
            MEDIA_ROOT=str(BACKEND / "private_media"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MEDIA_ROOT", result.stderr)

    def test_forces_owned_postgres_and_media_with_provider_disabled(self):
        result = run_probe(
            CHAMELEON_INTEGRATION="1",
            CHAMELEON_INTEGRATION_RUNTIME_DIR=str(SCRATCH),
            CHAMELEON_INTEGRATION_POSTGRES_PORT="55449",
            CHAMELEON_INTEGRATION_REDIS_PORT="56379",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["engine"].endswith("postgresql"))
        self.assertEqual(Path(data["name"]).name, "chameleon_integration")
        self.assertEqual(data["host"], "127.0.0.1")
        self.assertEqual(data["port"], "55449")
        self.assertTrue(Path(data["media"]).resolve().is_relative_to(SCRATCH))
