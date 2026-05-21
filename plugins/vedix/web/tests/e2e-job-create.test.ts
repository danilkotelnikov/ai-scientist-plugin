import { expect, test } from "@playwright/test";

/**
 * End-to-end happy path: fill the JobForm, submit it, and verify we
 * navigate to /jobs/:id. We stub the SaaS endpoints with route handlers
 * so the suite is hermetic and can run in CI without a live backend.
 */

test.describe("Vedix web — create job flow", () => {
  test.beforeEach(async ({ page }) => {
    // Seed a JWT so the API client attaches Authorization headers.
    await page.addInitScript(() => {
      window.localStorage.setItem("vedix_jwt", "test-token");
    });

    // Stub POST /v1/api/jobs → returns a fixed job id.
    await page.route(/\/v1\/api\/jobs(\?.*)?$/, async (route) => {
      const req = route.request();
      if (req.method() === "POST") {
        const body = JSON.parse(req.postData() ?? "{}");
        expect(body.topic).toContain("entropy");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            job_id: "11111111-1111-1111-1111-111111111111",
            state: "queued",
          }),
        });
      } else {
        // GET /v1/api/jobs (list) → empty list for the dashboard.
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: "[]",
        });
      }
    });

    // Stub GET /v1/api/jobs/:id → returns a queued status.
    await page.route(/\/v1\/api\/jobs\/[0-9a-f-]+$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "11111111-1111-1111-1111-111111111111",
          state: "queued",
          phase: null,
          progress: 0,
        }),
      });
    });

    // Stub the SSE stream so EventSource doesn't keep retrying.
    await page.route(/\/v1\/api\/jobs\/[0-9a-f-]+\/events.*$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "event: phase_start\ndata: {\"phase\":\"ideation\"}\n\n",
      });
    });
  });

  test("submits a job and navigates to the detail page", async ({ page }) => {
    await page.goto("/jobs/new");

    await page.getByLabel("Topic").fill(
      "Investigate the role of entropy regularization in transformer training",
    );
    await page.getByLabel("Primary metric").fill("perplexity");

    await page.getByRole("button", { name: /run pipeline/i }).click();

    await page.waitForURL(/\/jobs\/[0-9a-f-]+/);
    await expect(page.getByText(/Job 11111111…/i)).toBeVisible();
    await expect(page.getByText(/Live progress/i)).toBeVisible();
  });

  test("dashboard shows empty state when no jobs exist", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/No jobs yet/i)).toBeVisible();
  });

  test("new-job navigation works from the navbar", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "New job" }).first().click();
    await expect(page.getByText(/New research job/i)).toBeVisible();
  });
});
