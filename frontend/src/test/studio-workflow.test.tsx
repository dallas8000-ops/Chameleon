import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createAppRouter } from "../app/router";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const project = {
  id: 5,
  workspace_id: 11,
  title: "Launch teaser",
  format: "9:16",
  status: "draft",
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  scenes: [{ id: 1, project_id: 5, order_index: 0, kind: "script", title: "Intro", script_text: "", config: {} }],
  captions: [{ id: 9, project_id: 5, language: "en", segments: [{ start: 0, end: 2, text: "Hello" }], style: {}, updated_at: "x" }],
};
const csrf = { "GET /api/auth/csrf/": json({ csrfToken: "t" }) };

function renderAt(path: string) {
  return render(<RouterProvider router={createAppRouter([path])} />);
}

beforeEach(() => {
  clearCsrfToken();
  resetSessionStore();
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("shows provider setup state instead of fake success", async () => {
  installFetch({
    ...csrf,
    "GET /api/projects/5/": json(project),
    "POST /api/jobs/image-generation/": json({ code: "provider_not_configured", message: "Not configured", errors: {}, status: "blocked_provider_not_configured" }, 409),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  await user.click(await screen.findByRole("button", { name: /generate image/i }));

  expect(await screen.findByText(/configure magic hour api key/i)).toBeTruthy();
  expect(screen.getByText("blocked_provider_not_configured")).toBeTruthy();
});

test("saves edited caption segments via PATCH", async () => {
  const { calls } = installFetch({
    ...csrf,
    "GET /api/projects/5/": json(project),
    "PATCH /api/captions/9/": json({ ...project.captions[0], segments: [{ start: 0, end: 2, text: "Hi there" }] }),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  const text = await screen.findByLabelText("Segment 1 text");
  await user.clear(text);
  await user.type(text, "Hi there");
  await user.click(screen.getByRole("button", { name: /save captions/i }));

  expect(await screen.findByText("Captions saved.")).toBeTruthy();
  const patch = calls.find((call) => call.method === "PATCH")!;
  expect(JSON.parse(String(patch.body))).toEqual({ segments: [{ start: 0, end: 2, text: "Hi there" }] });
});

test("adds an image scene with asset reference and default duration", async () => {
  const { calls } = installFetch({
    ...csrf,
    "GET /api/projects/5/": json(project),
    "POST /api/projects/5/scenes/": json({ id: 2, project_id: 5, order_index: 1, kind: "image", title: "Hero", script_text: "", config: {} }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  await user.type(await screen.findByLabelText("Scene title"), "Hero");
  await user.selectOptions(screen.getByLabelText("Scene kind"), "image");
  await user.type(screen.getByLabelText("Private asset ID"), "42");
  await user.click(screen.getByRole("button", { name: /add scene/i }));

  expect(await screen.findByText("Hero")).toBeTruthy();
  const post = calls.find((call) => call.method === "POST" && call.url.endsWith("/scenes/"))!;
  expect(JSON.parse(String(post.body)).config).toEqual({ asset_id: 42, duration_seconds: 5 });
});

test("queues an export and shows only real status", async () => {
  const { calls } = installFetch({
    ...csrf,
    "POST /api/projects/5/exports/": json({ id: 3, project_id: 5, status: "queued", format: "9:16", settings: {}, error_code: "", error_message: "", video_available: false, subtitles_available: false, created_at: "", updated_at: "" }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/export");

  await user.click(screen.getByRole("button", { name: /queue export/i }));

  expect(await screen.findByText("Export status: queued")).toBeTruthy();
  expect(screen.queryByText(/download video/i)).toBeNull();
  expect(JSON.parse(String(calls.find((c) => c.method === "POST" && c.url.includes("exports"))!.body))).toEqual({ burn_captions: true });
});

