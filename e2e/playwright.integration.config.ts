import { defineConfig } from "@playwright/test";

const webPort = process.env.INTEGRATION_WEB_PORT ?? "15174";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./.runtime-results-integration",
  timeout: 120_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    channel: process.env.PLAYWRIGHT_CHANNEL,
  },
  webServer: {
    command: "node scripts/start-integration-stack.mjs",
    url: `http://127.0.0.1:${webPort}/`,
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
