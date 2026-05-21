import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for Vedix web e2e tests. Spins up the Vite dev server
 * on demand so the suite is hermetic.
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: /.*e2e.*\.test\.ts$/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 60_000,
  use: {
    baseURL: process.env.VEDIX_WEB_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.VEDIX_WEB_URL
    ? undefined
    : {
        command: "npm run dev",
        port: 5173,
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
