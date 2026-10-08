import contextlib
import json
import tempfile
import tomllib
from io import StringIO
from pathlib import Path

from django.conf import settings as django_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import resolve

from api.deployment_checks import collect_deployment_problems
from chameleon.settings import (
    RAILWAY_HEALTHCHECK_HOST,
    immutable_vite_asset,
    with_healthcheck_host,
)


class HealthEndpointTest(TestCase):
    def test_health_endpoint_returns_ok(self):
        res = self.client.get('/api/health/')
        # Expect 200 with JSON {"status": "ok"}
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get('status'), 'ok')

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_health_endpoint_is_exempt_from_ssl_redirect(self):
        res = self.client.get('/api/health/')
        self.assertEqual(res.status_code, 200)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_other_api_endpoints_still_redirect_to_https(self):
        res = self.client.get('/api/auth/session/')
        self.assertEqual(res.status_code, 301)
        self.assertTrue(res['Location'].startswith('https://'))


class SpaFallbackTest(TestCase):
    def setUp(self):
        self._dist = tempfile.TemporaryDirectory()
        self.addCleanup(self._dist.cleanup)
        Path(self._dist.name, 'index.html').write_text(
            '<!doctype html><title>Chameleon</title>', encoding='utf-8'
        )

    @contextlib.contextmanager
    def built_frontend(self):
        with self.settings(FRONTEND_DIST_DIR=self._dist.name):
            yield

    def test_client_route_serves_index_document(self):
        with self.built_frontend():
            res = self.client.get('/studio/7')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'text/html')
        self.assertIn('Chameleon', res.content.decode())
        self.assertIn('no-store', res['Cache-Control'])

    def test_root_serves_index_document(self):
        with self.built_frontend():
            res = self.client.get('/')
        self.assertEqual(res.status_code, 200)

    def test_unknown_api_route_is_not_swallowed_by_the_fallback(self):
        with self.built_frontend():
            res = self.client.get('/api/does-not-exist/')
        self.assertEqual(res.status_code, 404)
        self.assertNotIn('Chameleon', res.content.decode())

    def test_missing_bundle_reports_unavailable_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.settings(FRONTEND_DIST_DIR=empty):
                res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 503)
        self.assertIn('Frontend bundle is not available', res.content.decode())

    def test_missing_hashed_asset_is_not_answered_with_the_entry_document(self):
        with self.built_frontend():
            res = self.client.get('/assets/index-deadbeef.js')
        self.assertEqual(res.status_code, 404)

    def test_unsafe_methods_are_rejected(self):
        with self.built_frontend():
            res = self.client.post('/dashboard')
        self.assertEqual(res.status_code, 405)


class StaticAssetCachingTest(TestCase):
    def test_hashed_vite_bundles_are_treated_as_immutable(self):
        self.assertTrue(immutable_vite_asset(None, '/assets/index-DaJGsF9n.js'))
        self.assertTrue(immutable_vite_asset(None, '/assets/index-CqIiGVZ3.css'))

    def test_unhashed_files_are_not_immutable(self):
        self.assertFalse(immutable_vite_asset(None, '/index.html'))
        self.assertFalse(immutable_vite_asset(None, '/favicon.ico'))
        self.assertFalse(immutable_vite_asset(None, '/assets/logo.svg'))

    def test_entry_document_is_not_served_by_whitenoise(self):
        # WhiteNoise's directory index would cache the entry document; the SPA view must win.
        self.assertFalse(django_settings.WHITENOISE_INDEX_FILE)


class AllowedHostsTest(TestCase):
    def test_configured_hosts_also_admit_the_railway_probe(self):
        self.assertEqual(
            with_healthcheck_host(['chameleon.example.com']),
            ['chameleon.example.com', RAILWAY_HEALTHCHECK_HOST],
        )

    def test_probe_host_is_not_duplicated(self):
        hosts = ['chameleon.example.com', RAILWAY_HEALTHCHECK_HOST]
        self.assertEqual(with_healthcheck_host(hosts), hosts)

    def test_empty_host_list_is_left_alone(self):
        # An empty list means local development, where Django already allows localhost.
        self.assertEqual(with_healthcheck_host([]), [])


class ProductionSettingsMixin:
    """Supplies a deployment-shaped settings baseline backed by real temp directories."""

    def setUp(self):
        super().setUp()
        self._media = tempfile.TemporaryDirectory()
        self._bundle = tempfile.TemporaryDirectory()
        self._static = tempfile.TemporaryDirectory()
        Path(self._bundle.name, 'index.html').write_text('<!doctype html>', encoding='utf-8')
        self.addCleanup(self._media.cleanup)
        self.addCleanup(self._bundle.cleanup)
        self.addCleanup(self._static.cleanup)

    def settings_for(self, **overrides):
        baseline = {
            'DEBUG': False,
            'SECRET_KEY': 'k' * 64,
            'ALLOWED_HOSTS': ['chameleon.example.com', django_settings.RAILWAY_HEALTHCHECK_HOST],
            'CSRF_TRUSTED_ORIGINS': ['https://chameleon.example.com'],
            'SESSION_COOKIE_SECURE': True,
            'CSRF_COOKIE_SECURE': True,
            'SECURE_SSL_REDIRECT': True,
            'SECURE_HSTS_SECONDS': 31536000,
            'SECURE_PROXY_SSL_HEADER': ('HTTP_X_FORWARDED_PROTO', 'https'),
            'DATABASES': {
                'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'chameleon'}
            },
            'CACHES': {
                'default': {
                    'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                    'LOCATION': 'redis://redis.railway.internal:6379/0',
                }
            },
            'CELERY_BROKER_URL': 'redis://redis.railway.internal:6379/0',
            'MAGIC_HOUR_API_KEY': '',
            'MAGIC_HOUR_WEBHOOK_SECRET': '',
            'GENERATION_DOWNLOAD_ORIGINS': [],
            'GENERATION_STORAGE_CONFIRMED': False,
            'FFMPEG_BINARY': 'ffmpeg',
            'FFPROBE_BINARY': 'ffprobe',
            'MEDIA_ROOT': self._media.name,
            'FRONTEND_DIST_DIR': self._bundle.name,
            'STATIC_ROOT': self._static.name,
        }
        baseline.update(overrides)
        return baseline


class DeploymentCheckTest(ProductionSettingsMixin, TestCase):
    def test_well_formed_production_configuration_has_no_problems(self):
        with self.settings(**self.settings_for()):
            self.assertEqual(collect_deployment_problems('web'), [])

    def test_debug_and_placeholder_secret_are_reported(self):
        with self.settings(**self.settings_for(DEBUG=True, SECRET_KEY='test-secret')):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('DEBUG' in problem for problem in problems))
        self.assertTrue(any('SECRET_KEY' in problem for problem in problems))

    def test_short_secret_key_is_reported(self):
        with self.settings(**self.settings_for(SECRET_KEY='short')):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('at least 50 characters' in problem for problem in problems))

    def test_host_and_origin_problems_are_reported(self):
        with self.settings(
            **self.settings_for(
                ALLOWED_HOSTS=['*'],
                CSRF_TRUSTED_ORIGINS=['http://chameleon.example.com'],
            )
        ):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('wildcard' in problem for problem in problems))
        self.assertTrue(any('must use https' in problem for problem in problems))

    def test_insecure_cookies_and_missing_ssl_redirect_are_reported(self):
        with self.settings(
            **self.settings_for(
                SESSION_COOKIE_SECURE=False,
                CSRF_COOKIE_SECURE=False,
                SECURE_SSL_REDIRECT=False,
                SECURE_HSTS_SECONDS=0,
            )
        ):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('SESSION_COOKIE_SECURE' in problem for problem in problems))
        self.assertTrue(any('CSRF_COOKIE_SECURE' in problem for problem in problems))
        self.assertTrue(any('SECURE_SSL_REDIRECT' in problem for problem in problems))
        self.assertTrue(any('SECURE_HSTS_SECONDS' in problem for problem in problems))

    def test_sqlite_and_local_memory_cache_are_rejected(self):
        with self.settings(
            **self.settings_for(
                DATABASES={
                    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
                },
                CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
            )
        ):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('PostgreSQL' in problem for problem in problems))
        self.assertTrue(any('Redis' in problem for problem in problems))

    def test_localhost_broker_is_rejected(self):
        with self.settings(**self.settings_for(CELERY_BROKER_URL='redis://localhost:6379/0')):
            problems = collect_deployment_problems('worker')
        self.assertTrue(any('localhost' in problem for problem in problems))

    def test_media_root_inside_the_application_directory_is_rejected(self):
        ephemeral = Path(django_settings.BASE_DIR) / 'private_media'
        with self.settings(**self.settings_for(MEDIA_ROOT=str(ephemeral))):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('persistent volume' in problem for problem in problems))

    def test_relative_media_root_is_rejected(self):
        with self.settings(**self.settings_for(MEDIA_ROOT='private_media')):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('absolute path' in problem for problem in problems))

    def test_missing_frontend_bundle_is_reported_for_web_only(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.settings(**self.settings_for(FRONTEND_DIST_DIR=empty)):
                web_problems = collect_deployment_problems('web')
                worker_problems = collect_deployment_problems('worker')
        self.assertTrue(any('Frontend bundle missing' in problem for problem in web_problems))
        self.assertFalse(any('Frontend bundle missing' in problem for problem in worker_problems))

    def test_uncollected_static_root_is_reported_for_web_only(self):
        missing = str(Path(self._static.name, 'never-collected'))
        with self.settings(**self.settings_for(STATIC_ROOT=missing)):
            web_problems = collect_deployment_problems('web')
            worker_problems = collect_deployment_problems('worker')
        self.assertTrue(any('STATIC_ROOT' in problem for problem in web_problems))
        self.assertFalse(any('STATIC_ROOT' in problem for problem in worker_problems))

    def test_allowed_hosts_must_admit_the_railway_health_probe(self):
        with self.settings(**self.settings_for(ALLOWED_HOSTS=['chameleon.example.com'])):
            problems = collect_deployment_problems('web')
        self.assertTrue(
            any(django_settings.RAILWAY_HEALTHCHECK_HOST in problem for problem in problems)
        )

    def test_missing_ffmpeg_is_reported_for_worker_only(self):
        with self.settings(
            **self.settings_for(
                FFMPEG_BINARY='chameleon-missing-ffmpeg',
                FFPROBE_BINARY='chameleon-missing-ffprobe',
            )
        ):
            worker_problems = collect_deployment_problems('worker')
            web_problems = collect_deployment_problems('web')
        self.assertTrue(any('FFmpeg binary' in problem for problem in worker_problems))
        self.assertTrue(any('FFprobe binary' in problem for problem in worker_problems))
        self.assertFalse(any('FFmpeg binary' in problem for problem in web_problems))

    def test_provider_key_requires_verified_gates(self):
        with self.settings(**self.settings_for(MAGIC_HOUR_API_KEY='live-key')):
            problems = collect_deployment_problems('web')
        self.assertTrue(any('GENERATION_DOWNLOAD_ORIGINS' in problem for problem in problems))
        self.assertTrue(any('GENERATION_STORAGE_CONFIRMED' in problem for problem in problems))
        self.assertTrue(any('MAGIC_HOUR_WEBHOOK_SECRET' in problem for problem in problems))

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            collect_deployment_problems('database')

    def test_unwritable_media_root_is_reported_for_web_but_not_beat(self):
        with tempfile.TemporaryDirectory() as parent:
            blocker = Path(parent, 'not-a-directory')
            blocker.write_bytes(b'')
            unwritable = str(blocker / 'private_media')
            with self.settings(**self.settings_for(MEDIA_ROOT=unwritable)):
                web_problems = collect_deployment_problems('web')
                beat_problems = collect_deployment_problems('beat')
        self.assertTrue(any('not writable' in problem for problem in web_problems))
        self.assertFalse(any('not writable' in problem for problem in beat_problems))


class DeploymentManifestTest(TestCase):
    """The committed Railway manifests must stay consistent with the application."""

    @property
    def repo_root(self) -> Path:
        return Path(django_settings.BASE_DIR).parent

    def railway_config(self) -> dict:
        return json.loads(Path(self.repo_root, 'railway.json').read_text(encoding='utf-8'))

    def procfile_commands(self) -> dict:
        commands = {}
        for line in Path(self.repo_root, 'Procfile').read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name, _, command = line.partition(':')
            commands[name.strip()] = command.strip()
        return commands

    def test_healthcheck_path_resolves_to_the_health_endpoint(self):
        path = self.railway_config()['deploy']['healthcheckPath']
        self.assertEqual(resolve(path).url_name, 'health')

    def test_release_step_migrates_and_verifies_configuration(self):
        pre_deploy = self.railway_config()['deploy']['preDeployCommand']
        self.assertIn('manage.py migrate --noinput', pre_deploy)
        self.assertIn('manage.py check_deployment', pre_deploy)

    def test_start_command_supervises_the_procfile(self):
        start = self.railway_config()['deploy']['startCommand']
        self.assertIn('honcho start', start)
        self.assertIn('Procfile', start)

    def test_single_replica_keeps_beat_a_singleton(self):
        self.assertEqual(self.railway_config()['deploy']['numReplicas'], 1)

    def test_procfile_runs_the_api_worker_and_beat(self):
        commands = self.procfile_commands()
        self.assertEqual(set(commands), {'web', 'worker', 'beat'})
        self.assertIn('gunicorn chameleon.wsgi:application', commands['web'])
        self.assertIn('celery -A chameleon worker', commands['worker'])
        self.assertIn('celery -A chameleon beat', commands['beat'])

    def test_beat_schedule_is_written_outside_the_rebuilt_application_directory(self):
        self.assertIn('/data/celerybeat-schedule', self.procfile_commands()['beat'])

    def test_build_installs_ffmpeg_and_the_frontend_bundle(self):
        config = tomllib.loads(Path(self.repo_root, 'nixpacks.toml').read_text(encoding='utf-8'))
        self.assertIn('ffmpeg', config['phases']['setup']['nixPkgs'])
        install = ' '.join(config['phases']['install']['cmds'])
        self.assertIn('backend/requirements.txt', install)
        self.assertIn('npm --prefix frontend ci', install)
        build = ' '.join(config['phases']['build']['cmds'])
        self.assertIn('npm --prefix frontend run build', build)
        self.assertIn('collectstatic --noinput', build)
        # Vite, React and TypeScript are devDependencies, so the build toolchain
        # disappears if npm installs in production mode.
        self.assertNotIn('NODE_ENV', config.get('variables', {}))

    def test_processes_are_restarted_even_when_a_child_exits_cleanly(self):
        self.assertEqual(self.railway_config()['deploy']['restartPolicyType'], 'ALWAYS')

    def test_runtime_dependencies_are_declared(self):
        requirements = Path(self.repo_root, 'backend', 'requirements.txt').read_text(encoding='utf-8')
        for package in ('gunicorn', 'whitenoise', 'honcho'):
            self.assertIn(package, requirements)


class CheckDeploymentCommandTest(ProductionSettingsMixin, TestCase):
    def test_command_succeeds_on_a_valid_configuration(self):
        out = StringIO()
        with self.settings(**self.settings_for()):
            call_command('check_deployment', '--role', 'web', stdout=out)
        self.assertIn('looks correct', out.getvalue())

    def test_command_fails_and_lists_problems(self):
        err = StringIO()
        with self.settings(**self.settings_for(DEBUG=True)):
            with self.assertRaises(CommandError):
                call_command('check_deployment', '--role', 'web', stderr=err)
        self.assertIn('DEBUG', err.getvalue())
