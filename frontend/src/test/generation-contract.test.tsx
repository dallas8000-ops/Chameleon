import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { GenerationPanel } from "../features/studio/GenerationPanel";
import { clearCsrfToken } from "../lib/api/client";
import { installFetch, json } from "./fetch-mock";
import { resetSessionStore, useSessionStore } from "../lib/auth/session-store";

afterEach(() => { vi.restoreAllMocks(); clearCsrfToken(); sessionStorage.clear(); resetSessionStore(); });
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
    "POST /api/jobs/image-generation/": json({ code: "quote_changed", message: "Get a new quote.", errors: {},
      submission_not_accepted: true }, 409),
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

test.each([
  [202, "invalid_response"], [404, "not_found"], [429, "http_429"],
  [409, "quote_changed"], [409, "quote_expired"], [401, "not_authenticated"],
  [403, "workspace_read_only"], [503, "provider_unavailable"],
])("unconfirmed %s %s retains exact attempt through refresh and explicit resolution", async (status, code) => {
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": [
      json({ code, message: "Unconfirmed response", errors: {} }, status),
      json({ id: 77, status: "failed", error_message: "Operator review required" }, 202),
    ],
  });
  const user = userEvent.setup();
  const first = render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/submission outcome is unknown/);
  const saved = sessionStorage.getItem("generation-attempt:session:11:none");
  expect(saved).toBeTruthy();
  first.unmount();
  render(<GenerationPanel workspaceId={11} />);
  await user.click(await screen.findByRole("button", { name: "Resolve existing attempt" }));
  await screen.findByText("Operator review required");
  const posts = calls.filter(call => call.url === "/api/jobs/image-generation/");
  expect(posts).toHaveLength(2);
  expect(posts[0].body).toBe(posts[1].body);
  expect(posts[0].headers.get("Idempotency-Key")).toBe(posts[1].headers.get("Idempotency-Key"));
});

test("unknown attempt survives a stale resolution response without requoting or new identity", async () => {
  const { calls } = installFetch({
    ...base,
    "POST /api/jobs/image-generation/": [
      new Error("lost"), json({ code: "quote_expired", message: "Stale response", errors: {} }, 409),
      json({ id: 77, status: "failed", error_message: "Do not regenerate" }, 202),
    ],
  });
  const user = userEvent.setup();
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await user.click(await screen.findByRole("button", { name: "Resolve existing attempt" }));
  await screen.findByText("Stale response");
  expect(screen.getByRole("button", { name: "Resolve existing attempt" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Resolve existing attempt" }));
  await screen.findByText("Do not regenerate");
  const posts = calls.filter(call => call.url === "/api/jobs/image-generation/");
  expect(new Set(posts.map(post => post.body)).size).toBe(1);
  expect(new Set(posts.map(post => post.headers.get("Idempotency-Key"))).size).toBe(1);
});

test("confirmed accepted reconciliation job stays visible after refresh without another paid attempt", async () => {
  const { calls } = installFetch({
    ...base, "POST /api/jobs/image-generation/": json({
      id: 77, status: "failed", error_message: "Operator reconciliation required",
    }, 202),
  });
  const user = userEvent.setup();
  const first = render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText("Operator reconciliation required");
  first.unmount();
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText("Operator reconciliation required");
  expect((screen.getByRole("button", { name: "Generate image" }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter(call => call.url === "/api/jobs/image-generation/")).toHaveLength(1);
});

test("unknown identity survives sign-out and same-user sign-in and does not transfer to another user", async () => {
  useSessionStore.setState({ user: { id: 1, email: "owner@example.com" }, status: "authenticated" });
  const { calls } = installFetch({
    ...base, "POST /api/jobs/image-generation/": [
      new Error("lost"), json({ id: 77, status: "failed", error_message: "Same owner attempt" }, 202),
    ],
  });
  const user = userEvent.setup();
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/submission outcome is unknown/);
  const identity = sessionStorage.getItem("generation-attempt:1:11:none");
  act(() => useSessionStore.setState({ user: null, status: "anonymous" }));
  act(() => useSessionStore.setState({ user: { id: 2, email: "other@example.com" }, status: "authenticated" }));
  expect(screen.queryByRole("button", { name: "Resolve existing attempt" })).toBeNull();
  expect(sessionStorage.getItem("generation-attempt:1:11:none")).toBe(identity);
  act(() => useSessionStore.setState({ user: { id: 1, email: "owner@example.com" }, status: "authenticated" }));
  await user.click(await screen.findByRole("button", { name: "Resolve existing attempt" }));
  await screen.findByText("Same owner attempt");
  const posts = calls.filter(call => call.url === "/api/jobs/image-generation/");
  expect(posts[0].body).toBe(posts[1].body);
  expect(posts[0].headers.get("Idempotency-Key")).toBe(posts[1].headers.get("Idempotency-Key"));
});

test("a late accepted response stays in its original workspace across context changes", async () => {
  let release: ((response: Response) => void) | undefined;
  const { calls } = installFetch({
    ...base,
    "GET /api/jobs/capabilities/?workspace_id=22": json(capabilities),
    "POST /api/jobs/image-generation/": () => new Promise<Response>(resolve => { release = resolve; }),
  });
  const user = userEvent.setup();
  const view = render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await waitFor(() => expect(release).toBeTruthy());
  view.rerender(<GenerationPanel workspaceId={22} />);
  await act(async () => release!(json({ id: 77, status: "failed", error_message: "Workspace eleven reconciliation" }, 202)));
  expect(screen.queryByText("Workspace eleven reconciliation")).toBeNull();
  expect(sessionStorage.getItem("generation-attempt:session:22:none")).toBeNull();
  view.rerender(<GenerationPanel workspaceId={11} />);
  await screen.findByText("Workspace eleven reconciliation");
  expect(calls.filter(call => call.url === "/api/jobs/image-generation/")).toHaveLength(1);
});

test("unreadable accepted response retains identity instead of treating HTTP success as rejection", async () => {
  installFetch({ ...base, "POST /api/jobs/image-generation/": new Response("{broken", { status: 202 }) });
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/5 credits/);
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/submission outcome is unknown/);
  expect(sessionStorage.getItem("generation-attempt:session:11:none")).toBeTruthy();
});

test("a saved successful image allows a new estimate only after an explicit action, never on failure", async () => {
  const { calls } = installFetch({
    ...base, "POST /api/jobs/image-generation/": json({ id: 77, status: "queued" }, 202),
    "GET /api/jobs/77/": json({ id: 77, status: "completed", asset_status: "ready", result: { asset_id: 42 } }),
  });
  const user = userEvent.setup();
  render(<GenerationPanel workspaceId={11} pollIntervalMs={10} />);
  await screen.findByText(/5 credits/);
  await user.click(screen.getByRole("button", { name: "Generate image" }));
  await screen.findByText(/Saved as workspace asset #42/);
  expect(calls.filter(call => call.url.endsWith("/quote/"))).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "Refresh estimate" }));
  await screen.findByText(/Estimated cost: 5 credits/);
  expect(calls.filter(call => call.url === "/api/jobs/image-generation/")).toHaveLength(1);
});

test("unreadable saved identity fails closed rather than allowing a replacement paid attempt", async () => {
  sessionStorage.setItem("generation-attempt:session:11:none", "{broken");
  const { calls } = installFetch(base);
  render(<GenerationPanel workspaceId={11} />);
  await screen.findByText(/Unable to restore submission identity/);
  expect((screen.getByRole("button", { name: "Generate image" }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter(call => call.url.endsWith("/quote/"))).toHaveLength(0);
});
