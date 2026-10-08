import { defineConfig } from "@playwright/test";

const apiPort = process.env.E2E_API_PORT ?? "18000";
const webPort = process.env.E2E_WEB_PORT ?? "15173";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./.runtime-results",
  timeout: 120_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    channel: process.env.PLAYWRIGHT_CHANNEL,
  },
  webServer: [
    {
      command: "node scripts/start-backend.mjs",
      url: `http://127.0.0.1:${apiPort}/api/health/`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npm --prefix ../frontend run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: `http://127.0.0.1:${webPort}/`,
      env: { BACKEND_URL: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
