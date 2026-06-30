const path = require("path");
const { defineConfig } = require("playwright/test");

const defaultBaseUrl = "http://139.59.158.77:8502";
const baseURL = process.env.SC_E2E_BASE_URL || defaultBaseUrl;

module.exports = defineConfig({
  testDir: path.join(__dirname, "specs"),
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(__dirname, "..", "..", ".Codex", "playwright-report"), open: "never" }],
    ["json", { outputFile: path.join(__dirname, "..", "..", ".Codex", "playwright-report", "results.json") }],
  ],
  use: {
    baseURL,
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
});
