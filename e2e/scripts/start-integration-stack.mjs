import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, createWriteStream, existsSync, mkdirSync, rmSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolvePython } from "./resolve-python.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const backend = path.join(root, "backend");
const frontend = path.join(root, "frontend");
const runtime = path.resolve(here, "..", ".runtime-integration");
const logsDir = path.join(runtime, "logs");
const pgData = path.join(runtime, "postgres");
const mediaDir = path.join(runtime, "media");
const redisDir = path.join(runtime, "redis");
const beatSchedulePath = path.join(runtime, "celerybeat-schedule");
const python = resolvePython({ root });
const node = process.execPath;
const pgPort = process.env.INTEGRATION_PG_PORT ?? "55449";
const redisPort = process.env.INTEGRATION_REDIS_PORT ?? "56379";
const apiPort = process.env.INTEGRATION_API_PORT ?? "18080";
const webPort = process.env.INTEGRATION_WEB_PORT ?? "15174";
const dbName = "chameleon_integration";
const children = [];
let stopping = false;

function fail(message) {
  console.error(message);
  process.exit(1);
}

function candidateExisting(paths) {
  return paths.find((candidate) => existsSync(candidate));
}

function locatePostgresBin() {
  const explicit = process.env.POSTGRES_BIN_DIR;
  const candidates = [
    explicit,
    "C:\\Program Files\\PostgreSQL\\16\\bin",
    "C:\\Program Files\\PostgreSQL\\15\\bin",
    "C:\\Program Files\\PostgreSQL\\14\\bin",
  ].filter(Boolean);
  const found = candidateExisting(candidates);
  if (!found) fail("PostgreSQL binaries not found. Set POSTGRES_BIN_DIR to an owned local installation.");
  return found;
}

function locateRedisExe() {
  const explicit = process.env.REDIS_SERVER_EXE;
  const found = candidateExisting([
    explicit,
    "C:\\Program Files\\Redis\\redis-server.exe",
  ].filter(Boolean));
  if (!found) fail("redis-server.exe not found. Set REDIS_SERVER_EXE to an owned local installation.");
  return found;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function assertPortFree(port, label) {
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", (error) => reject(new Error(`${label} port ${port} is unavailable: ${error.message}`)));
    server.listen({ host: "127.0.0.1", port: Number(port) }, () => server.close(resolve));
  });
}

async function waitForPort(port, label, timeoutMs = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const ready = await new Promise((resolve) => {
      const socket = net.connect({ host: "127.0.0.1", port: Number(port) });
      socket.once("connect", () => {
        socket.destroy();
        resolve(true);
      });
      socket.once("error", () => resolve(false));
    });
    if (ready) return;
    await wait(250);
  }
  throw new Error(`${label} did not start listening on port ${port} within ${timeoutMs}ms.`);
}

async function waitForHttp(url, label, timeoutMs = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // keep waiting
    }
    await wait(500);
  }
  throw new Error(`${label} did not become healthy at ${url} within ${timeoutMs}ms.`);
}

function runSyncOrFail(command, args, options, label) {
  const result = spawnSync(command, args, { ...options, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(`${label} failed (${result.status}).\nSTDOUT:\n${result.stdout ?? ""}\nSTDERR:\n${result.stderr ?? ""}`);
  }
}

function spawnLogged(name, command, args, options = {}) {
  const stdoutLog = createWriteStream(path.join(logsDir, `${name}.stdout.log`), { flags: "a" });
  const stderrLog = createWriteStream(path.join(logsDir, `${name}.stderr.log`), { flags: "a" });
  const child = spawn(command, args, { ...options, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child);
  child.stdout.on("data", (chunk) => {
    process.stdout.write(`[${name}] ${chunk}`);
    stdoutLog.write(chunk);
  });
  child.stderr.on("data", (chunk) => {
    process.stderr.write(`[${name}] ${chunk}`);
    stderrLog.write(chunk);
  });
  child.on("exit", (code, signal) => {
    stdoutLog.end();
    stderrLog.end();
    if (!stopping && code !== 0) {
      stopAll().finally(() => {
        console.error(`${name} exited unexpectedly with ${code ?? "null"} (${signal ?? "no-signal"}).`);
        process.exit(code ?? 1);
      });
    }
  });
  return child;
}

async function stopAll() {
  if (stopping) return;
  stopping = true;
  for (const child of [...children].reverse()) {
    if (!child.killed) {
      try {
        child.kill("SIGTERM");
      } catch {
        // best effort cleanup only
      }
    }
  }
  await wait(1_000);
  for (const child of [...children].reverse()) {
    if (child.exitCode === null) {
      try {
        child.kill("SIGKILL");
      } catch {
        // best effort cleanup only
      }
    }
  }
}

async function main() {
  for (const [port, label] of [
    [pgPort, "PostgreSQL"],
    [redisPort, "Redis"],
    [apiPort, "API"],
    [webPort, "Frontend"],
  ]) {
    await assertPortFree(port, label);
  }

  const postgresBin = locatePostgresBin();
  const redisExe = locateRedisExe();
  const postgresExe = path.join(postgresBin, "postgres.exe");
  const initdbExe = path.join(postgresBin, "initdb.exe");
  const createdbExe = path.join(postgresBin, "createdb.exe");
  const psqlExe = path.join(postgresBin, "psql.exe");
  const viteBin = path.join(frontend, "node_modules", "vite", "bin", "vite.js");
  if (!existsSync(viteBin)) fail("frontend node_modules/vite/bin/vite.js is missing; install frontend dependencies first.");

  rmSync(runtime, { recursive: true, force: true });
  mkdirSync(logsDir, { recursive: true });
  mkdirSync(mediaDir, { recursive: true });
  mkdirSync(redisDir, { recursive: true });

  runSyncOrFail(initdbExe, ["-D", pgData, "-U", "postgres", "-A", "trust", "-E", "UTF8"], {}, "initdb");
  const postgresConf = path.join(pgData, "postgresql.conf");
  appendFileSync(postgresConf, `\nlisten_addresses = '127.0.0.1'\nport = ${pgPort}\n`);

  const postgres = spawnLogged("postgres", postgresExe, ["-D", pgData], {
    env: { ...process.env, PGPORT: pgPort, PGDATA: pgData },
  });
  await waitForPort(pgPort, "PostgreSQL");
  runSyncOrFail(createdbExe, ["-h", "127.0.0.1", "-p", pgPort, "-U", "postgres", dbName], {}, "createdb");
  runSyncOrFail(psqlExe, ["-h", "127.0.0.1", "-p", pgPort, "-U", "postgres", "-d", dbName, "-c", "select 1;"], {}, "psql smoke");

  const redis = spawnLogged("redis", redisExe, [
    "--bind", "127.0.0.1",
    "--port", redisPort,
    "--save", "",
    "--appendonly", "no",
    "--dir", redisDir,
    "--dbfilename", "dump.rdb",
  ]);
  await waitForPort(redisPort, "Redis");

  const commonEnv = {
    ...process.env,
    CHAMELEON_INTEGRATION: "1",
    CHAMELEON_INTEGRATION_RUNTIME_DIR: runtime,
    CHAMELEON_INTEGRATION_POSTGRES_PORT: pgPort,
    CHAMELEON_INTEGRATION_REDIS_PORT: redisPort,
    DJANGO_SETTINGS_MODULE: "chameleon.settings_integration",
    SECRET_KEY: "integration-only-" + "x".repeat(40),
    DEBUG: "1",
    PYTHONUNBUFFERED: "1",
    DATABASE_URL: `postgresql://postgres@127.0.0.1:${pgPort}/${dbName}`,
    REDIS_URL: `redis://127.0.0.1:${redisPort}/15`,
    CELERY_BROKER_URL: `redis://127.0.0.1:${redisPort}/14`,
    ALLOWED_HOSTS: "127.0.0.1,localhost",
    CSRF_TRUSTED_ORIGINS: `http://127.0.0.1:${webPort}`,
    MEDIA_ROOT: mediaDir,
    FFMPEG_BINARY: path.join(root, "e2e", "node_modules", "ffmpeg-static", "ffmpeg.exe"),
    FFPROBE_BINARY: path.join(root, "e2e", "node_modules", "ffprobe-static", "bin", "win32", "x64", "ffprobe.exe"),
  };

  runSyncOrFail(
    python.command,
    [...python.args, "manage.py", "migrate", "--noinput"],
    { cwd: backend, env: commonEnv },
    "backend migrate",
  );

  const api = spawnLogged("api", python.command, [...python.args, "manage.py", "runserver", `127.0.0.1:${apiPort}`, "--noreload"], {
    cwd: backend,
    env: commonEnv,
  });
  const worker = spawnLogged("worker", python.command, [...python.args, "-m", "celery", "-A", "chameleon", "worker", "-P", "solo", "-l", "info"], {
    cwd: backend,
    env: commonEnv,
  });
  const beat = spawnLogged("beat", python.command, [
    ...python.args, "-m", "celery", "-A", "chameleon", "beat", "-l", "info", "-s", beatSchedulePath,
  ], {
    cwd: backend,
    env: commonEnv,
  });
  const frontendEnv = { ...process.env, BACKEND_URL: `http://127.0.0.1:${apiPort}` };
  const frontendServer = spawnLogged("frontend", node, [viteBin, "--host", "127.0.0.1", "--port", webPort, "--strictPort"], {
    cwd: frontend,
    env: frontendEnv,
  });

  await waitForHttp(`http://127.0.0.1:${apiPort}/api/health/`, "API");
  await waitForHttp(`http://127.0.0.1:${webPort}/`, "Frontend");

  console.log(
    JSON.stringify({
      runtime,
      ports: { postgres: Number(pgPort), redis: Number(redisPort), api: Number(apiPort), web: Number(webPort) },
      databaseUrl: commonEnv.DATABASE_URL,
      redisUrl: commonEnv.REDIS_URL,
      brokerUrl: commonEnv.CELERY_BROKER_URL,
    }),
  );

  process.on("SIGINT", () => stopAll().finally(() => process.exit(0)));
  process.on("SIGTERM", () => stopAll().finally(() => process.exit(0)));
  process.on("exit", () => {
    if (!stopping) {
      for (const child of children) {
        try {
          child.kill("SIGTERM");
        } catch {
          // best effort cleanup only
        }
      }
    }
  });

  void postgres;
  void redis;
  void api;
  void worker;
  void beat;
  void frontendServer;
}

main().catch((error) => {
  console.error(error.stack || String(error));
  stopAll().finally(() => process.exit(1));
});
