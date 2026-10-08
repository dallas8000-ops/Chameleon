import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { GenerationPanel } from "../features/studio/GenerationPanel";
import { clearCsrfToken } from "../lib/api/client";
import { installFetch, json } from "./fetch-mock";

afterEach(() => { vi.restoreAllMocks(); clearCsrfToken(); sessionStorage.clear(); });
const capabilities = { capabilities: [{ capability: "image.generate", available: true, can_submit: true }] };
const quote = {
  quote_id: "quote-1", estimated_credits: 5, pricing_version: "v1",
  expires_at: new Date(Date.now() + 300000).toISOString(), price_guaranteed: false,
  parameters: { model: "z-image-turbo", resolution: "640px", image_count: 1 },
  basis: { description: "Verified tariff" },
};
const base = {
  "GET /api/auth/csrf/": json({ csrfToken: "t" }),
  "GET /api/jobs/capabilities/?workspace_id=11": json(capabilities),
  "POST /api/jobs/image-generation/quote/": json(quote),
};

test("fetches a server quote and submits its identity only after explicit click", async () => {
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": json({ id: 77, status: "queued" }, 202),
    "GET /api/jobs/77/": json({ id: 77, status: "completed", asset_status: "ready", result: { asset_id: 42 } }),
  });
  render(<GenerationPanel workspaceId={11} pollIntervalMs={10} />);
  expect(await screen.findByText(/5 credits/)).toBeTruthy();
  expect(calls.filter(c => c.url === "/api/jobs/image-generation/")).toHaveLength(0);
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/Saved as workspace asset #42/);
  const submit = calls.find(c => c.url === "/api/jobs/image-generation/")!;
  expect(JSON.parse(String(submit.body)).quote_id).toBe("quote-1");
  expect(submit.headers.get("Idempotency-Key")).toBeTruthy();
});

test("stale submit requires another quote and explicit consent without automatic resubmission", async () => {
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": json({ code: "quote_changed", message: "Get a new quote.", errors: {} }, 409),
  });
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate image" }));
  await waitFor(() => expect(calls.filter(c => c.url.endsWith("/quote/")).length).toBe(2));
  expect(calls.filter(c => c.url === "/api/jobs/image-generation/")).toHaveLength(1);
});

test("lost submit response resolves the identical paid attempt rather than generating again", async () => {
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": [new Error("connection lost"), json({ id: 77, status: "queued" }, 202)],
    "GET /api/jobs/77/": json({ id: 77, status: "failed", error_message: "Operator review required" }),
  });
  const user = userEvent.setup();
  render(<GenerationPanel workspaceId={11} pollIntervalMs={10} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/submission outcome is unknown/);
  expect((screen.getByRole("button", { name: "Generate image" }) as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole("button", { name: "Resolve existing attempt" }));
  await screen.findByText("Operator review required");
  const posts = calls.filter(c => c.url === "/api/jobs/image-generation/");
  expect(posts).toHaveLength(2);
  expect(posts[0].headers.get("Idempotency-Key")).toBe(posts[1].headers.get("Idempotency-Key"));
  expect(posts[0].body).toBe(posts[1].body);
});

test("provider completion keeps polling until private asset readiness and refreshes assets once", async () => {
  const onReady = vi.fn();
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": json({ id: 77, status: "queued" }, 202),
    "GET /api/jobs/77/": [
      json({ id: 77, status: "completed", asset_status: "pending", result: {} }),
      json({ id: 77, status: "completed", asset_status: "ready", result: { asset_id: 42 } }),
    ],
  });
  render(<GenerationPanel workspaceId={11} pollIntervalMs={30} onAssetReady={onReady} />);
  await screen.findByText(/5 credits/);
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/Provider completed; saving private Asset/);
  await screen.findByText(/Saved as workspace asset #42/);
  expect(onReady).toHaveBeenCalledTimes(1);
  const count = calls.filter(c => c.url === "/api/jobs/77/").length;
  await new Promise(resolve => setTimeout(resolve, 100));
  expect(calls.filter(c => c.url === "/api/jobs/77/")).toHaveLength(count);
});

test("retry saving posts only to ingestion recovery, never generation", async () => {
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": json({ id: 77, status: "queued" }, 202),
    "GET /api/jobs/77/": [
      json({ id: 77, status: "completed", asset_status: "failed", asset_error_code: "result_download_failed", asset_retryable: true }),
      json({ id: 77, status: "completed", asset_status: "ready", result: { asset_id: 42 } }),
    ],
    "POST /api/jobs/77/asset-ingestion/retry/": json({ id: 77, status: "completed", asset_status: "pending", result: {} }, 202),
  });
  render(<GenerationPanel workspaceId={11} pollIntervalMs={10} />);
  await screen.findByText(/5 credits/);
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate image" }));
  await userEvent.setup().click(await screen.findByRole("button", { name: "Retry saving only" }));
  await screen.findByText(/Saved as workspace asset #42/);
  expect(calls.filter(c => c.url === "/api/jobs/image-generation/")).toHaveLength(1);
});

test("input change immediately removes quote and obsolete async quote responses cannot enable submit", async () => {
  let release: ((response: Response) => void) | undefined;
  installFetch({
    ...base,
    "POST /api/jobs/image-generation/quote/": [
      () => new Promise<Response>(resolve => { release = resolve; }),
      json({ ...quote, estimated_credits: 6 }),
    ],
  });
  render(<GenerationPanel workspaceId={11} />);
  await waitFor(() => expect(release).toBeTruthy());
  await userEvent.setup().type(screen.getByLabelText("Image prompt"), " another");
  expect((screen.getByRole("button", { name: "Generate image" }) as HTMLButtonElement).disabled).toBe(true);
  release!(json(quote));
  await screen.findByText(/6 credits/);
  expect(screen.queryByText(/Estimated cost: 5 credits/)).toBeNull();
});

test("expired quote never enables paid submission", async () => {
  const { calls } = installFetch({
    ...base, "POST /api/jobs/image-generation/quote/": json({ ...quote, expires_at: "2020-01-01T00:00:00Z" }),
  });
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/invalid or expired quote/);
  expect((screen.getByRole("button", { name: "Generate image" }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter(c => c.url === "/api/jobs/image-generation/")).toHaveLength(0);
});

test("an already failed accepted attempt shows reconciliation warning without losing its terminal error", async () => {
  installFetch({
    ...base,
    "POST /api/jobs/image-generation/": json({
      id: 77, status: "failed", error_code: "provider_submission_outcome_unknown",
      error_message: "Do not resubmit; operator reconciliation is required.",
    }, 202),
  });
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate image" }));
  expect(await screen.findByText(/operator reconciliation is required/)).toBeTruthy();
});
