import { expect, test } from "@playwright/test";

test("server quote consent, completed provider, private Asset readiness and scene/export flow", async ({ page }) => {
  let generated = 0;
  let reads = 0;
  let ready = false;
  const asset = { id: 42, workspace_id: 11, name: "Generated image", asset_type: "image", content_type: "image/png", size_bytes: 100 };
  const project = { id: 5, workspace_id: 11, title: "Image foundation", format: "9:16", scenes: [], captions: [] };
  await page.route(/\/api\/(?:auth|jobs|projects|assets)\//, async route => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    let body: unknown;
    if (url === "/api/auth/session/") body = { authenticated: true, user: { id: 1, email: "local@example.com" },
      workspaces: [{ id: 11, name: "Local", slug: "local", role: "owner" }] };
    else if (url === "/api/auth/csrf/") body = { csrfToken: "local-test" };
    else if (url === "/api/projects/5/") body = project;
    else if (url === "/api/assets/") body = ready ? [asset] : [];
    else if (url === "/api/jobs/capabilities/") body = { capabilities: [{ capability: "image.generate", available: true, can_submit: true }] };
    else if (url === "/api/jobs/image-generation/quote/") body = {
      quote_id: "quote-1", estimated_credits: 5, pricing_version: "test-v1", price_guaranteed: false,
      expires_at: new Date(Date.now() + 300000).toISOString(),
      parameters: { model: "z-image-turbo", resolution: "640px", image_count: 1 },
      basis: { description: "Operator verified local fixture" },
    };
    else if (url === "/api/jobs/image-generation/") {
      expect(request.postDataJSON().quote_id).toBe("quote-1");
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      generated++;
      body = { id: 77, status: "queued" };
    } else if (url === "/api/jobs/77/") {
      reads++;
      ready = reads >= 2;
      body = { id: 77, status: "completed", asset_status: ready ? "ready" : "pending",
        quoted_credits: 5, provider_reported_credits: 5, result: ready ? { asset_id: 42 } : {} };
    } else if (url === "/api/projects/5/scenes/") {
      expect(request.postDataJSON().config.asset_id).toBe(42);
      body = { id: 1, project_id: 5, order_index: 0, ...request.postDataJSON() };
    } else if (url === "/api/projects/5/exports/") body = {
      id: 3, project_id: 5, status: "queued", format: "9:16", settings: {},
      video_available: false, subtitles_available: false, error_message: "",
    };
    else throw new Error(`Unexpected local API fixture: ${url}`);
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/app/projects/5/studio");
  await expect(page.getByText(/Estimated cost: 5 credits/)).toBeVisible();
  expect(generated).toBe(0);
  await page.getByRole("button", { name: "Generate image", exact: true }).click();
  await expect(page.getByText(/Provider completed; saving private Asset/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Saved as workspace asset #42/)).toBeVisible({ timeout: 10000 });
  await page.getByLabel("Scene title").fill("Generated scene");
  await page.getByLabel("Scene kind").selectOption("image");
  await page.getByRole("combobox", { name: /Media asset/ }).selectOption("42");
  await page.getByRole("button", { name: "Add scene", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Generated scene (image)" })).toBeVisible();
  await page.getByRole("link", { name: "Go to export" }).click();
  await page.getByRole("button", { name: "Queue export", exact: true }).click();
  await expect(page.getByText("Export status: queued")).toBeVisible();
  expect(generated).toBe(1);
});
