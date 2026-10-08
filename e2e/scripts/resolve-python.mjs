// Portable Python resolution for the E2E backend: explicit override, repo .venv, then platform launchers.
import { spawnSync } from "node:child_process";
import path from "node:path";

export function candidatePythons({ root, env = process.env, platform = process.platform }) {
  if (env.E2E_PYTHON) {
    return [{ command: env.E2E_PYTHON, args: [], explicit: true }];
  }
  const win = platform === "win32";
  const p = win ? path.win32 : path.posix;
  const venv = win ? p.join(root, ".venv", "Scripts", "python.exe") : p.join(root, ".venv", "bin", "python");
  const rest = win
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];
  return [{ command: venv, args: [] }, ...rest];
}

const defaultProbe = (candidate) =>
  spawnSync(candidate.command, [...candidate.args, "-c", "import django, celery, rest_framework"], {
    stdio: "ignore",
  });

export function resolvePython({ root, env = process.env, platform = process.platform, probe = defaultProbe }) {
  const candidates = candidatePythons({ root, env, platform });
  for (const candidate of candidates) {
    if (probe(candidate).status === 0) {
      return candidate;
    }
  }
  const tried = candidates.map((c) => [c.command, ...c.args].join(" ")).join("; ");
  throw new Error(
    `No usable Python (needs Django, Celery and DRF installed; tried: ${tried}). ` +
      "Install backend/requirements.txt into the repo .venv or set E2E_PYTHON to a working interpreter.",
  );
}
