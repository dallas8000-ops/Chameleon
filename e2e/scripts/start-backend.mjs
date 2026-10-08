// Starts the isolated Django API for the Playwright harness (SQLite, eager Celery, scratch media).
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const backend = path.join(root, "backend");
const runtime = path.join(here, "..", ".runtime");
const python = process.env.E2E_PYTHON
  ?? "C:\\Users\\Ray\\AppData\\Local\\Programs\\Python\\Python311\\python.exe";
const apiPort = process.env.E2E_API_PORT ?? "18000";
const webPort = process.env.E2E_WEB_PORT ?? "15173";

// Only this exact scratch directory is ever reset.
rmSync(runtime, { recursive: true, force: true });
mkdirSync(path.join(runtime, "media"), { recursive: true });

const env = {
  ...process.env,
  CHAMELEON_E2E: "1",
  DJANGO_SETTINGS_MODULE: "chameleon.settings_e2e",
  SECRET_KEY: "e2e-only-" + "x".repeat(40),
  DEBUG: "1",
  DATABASE_URL: "sqlite:///" + path.join(runtime, "e2e.sqlite3").replaceAll("\\", "/"),
  REDIS_URL: "redis://127.0.0.1:1/0",
  CELERY_BROKER_URL: "memory://",
  ALLOWED_HOSTS: "127.0.0.1,localhost",
  CSRF_TRUSTED_ORIGINS: `http://127.0.0.1:${webPort}`,
  AUTH_THROTTLE_RATE: "1000/minute",
  MAGIC_HOUR_API_KEY: "",
  MEDIA_ROOT: path.join(runtime, "media"),
  FFMPEG_BINARY: require("ffmpeg-static"),
  FFPROBE_BINARY: require("ffprobe-static").path,
};

const migrate = spawnSync(python, ["manage.py", "migrate", "--noinput"], { cwd: backend, env, stdio: "inherit" });
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

const server = spawn(python, ["manage.py", "runserver", `127.0.0.1:${apiPort}`, "--noreload"], {
  cwd: backend, env, stdio: "inherit",
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill());
server.on("exit", (code) => process.exit(code ?? 0));
