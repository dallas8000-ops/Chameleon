import assert from "node:assert/strict";
import { test } from "node:test";

import { candidatePythons, resolvePython } from "./resolve-python.mjs";

const root = "/repo";
const ok = () => ({ status: 0 });

test("explicit E2E_PYTHON wins and is never silently replaced when invalid", () => {
  assert.deepEqual(candidatePythons({ root, env: { E2E_PYTHON: "/custom/python" }, platform: "linux" }), [
    { command: "/custom/python", args: [], explicit: true },
  ]);
  assert.throws(
    () => resolvePython({ root, env: { E2E_PYTHON: "/nope" }, platform: "linux", probe: () => ({ status: 1 }) }),
    /E2E_PYTHON/,
  );
});

test("prefers repo .venv, then platform launchers, with no user-home paths", () => {
  const win = candidatePythons({ root: "C:\\repo", env: {}, platform: "win32" });
  assert.match(win[0].command, /\.venv.Scripts.python\.exe$/);
  assert.deepEqual(win.slice(1).map((c) => [c.command, ...c.args]), [["py", "-3"], ["python"]]);
  const nix = candidatePythons({ root, env: {}, platform: "linux" });
  assert.match(nix[0].command, /\.venv.bin.python$/);
  assert.deepEqual(nix.slice(1).map((c) => c.command), ["python3", "python"]);
  for (const c of [...win, ...nix]) assert.doesNotMatch(c.command, /Users/);
});

test("first candidate that can import Django and Celery is used", () => {
  const seen = [];
  const picked = resolvePython({
    root, env: {}, platform: "linux",
    probe: (c) => { seen.push(c.command); return c.command === "python3" ? ok() : { status: 1 }; },
  });
  assert.equal(picked.command, "python3");
  assert.equal(seen.length, 2);
});

test("fails with guidance when nothing works", () => {
  assert.throws(() => resolvePython({ root, env: {}, platform: "linux", probe: () => ({ status: 1 }) }), /E2E_PYTHON/);
});
