import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./.playwright-results",
  use: { baseURL: "http://127.0.0.1:4178", browserName: "chromium", channel: process.env.PLAYWRIGHT_CHANNEL },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4178",
    url: "http://127.0.0.1:4178", reuseExistingServer: false,
  },
});
