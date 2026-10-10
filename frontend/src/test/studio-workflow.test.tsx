import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createAppRouter } from "../app/router";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const caption = { id: 9, project_id: 5, language: "en", segments: [{ start: 0, end: 2, text: "Hello" }], style: {}, updated_at: "x" };
const project = {
  id: 5,
  workspace_id: 11,
  title: "Launch teaser",
  format: "9:16",
  status: "draft",
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  scenes: [{ id: 1, project_id: 5, order_index: 0, kind: "script", title: "Intro", script_text: "", config: {} }],
  captions: [caption],
};
const photo = { id: 42, workspace_id: 11, asset_type: "image", source: "upload", name: "Hero photo", content_type: "image/png", size_bytes: 10, created_at: "x" };
const owner = { id: 1, email: "o@example.com" };
const studio = { id: 11, name: "Studio", slug: "studio", role: "owner" };
const csrf = {
  "GET /api/auth/csrf/": json({ csrfToken: "t" }),
  "GET /api/auth/session/": json({ authenticated: true, user: owner, workspaces: [studio] }),
};
const baseRoutes = {
  ...csrf,
  "GET /api/projects/5/": json(project),
  "GET /api/assets/?workspace_id=11": json([photo]),
};
const exportRecord = { id: 3, project_id: 5, status: "queued", format: "9:16", settings: {}, error_code: "", error_message: "", video_available: false, subtitles_available: false, created_at: "", updated_at: "" };

function renderAt(path: string) {
  return render(<RouterProvider router={createAppRouter([path])} />);
}

beforeEach(() => {
  clearCsrfToken();
  resetSessionStore();
  sessionStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("signing out posts to the logout endpoint and returns to sign in", async () => {
  const { calls } = installFetch({ ...baseRoutes, "POST /api/auth/logout/": json({}, 200) });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  await user.click(await screen.findByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("button", { name: /sign in/i })).toBeTruthy();
  expect(calls.some((call) => call.method === "POST" && call.url === "/api/auth/logout/")).toBe(true);
});

test("uploads a private asset with multipart form data and lists it", async () => {
  const { calls } = installFetch({
    ...baseRoutes,
    "POST /api/assets/": json({ ...photo, id: 43, name: "Uploaded" }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  await screen.findByText("Hero photo");
  await user.upload(screen.getByLabelText("Upload media"), new File(["x"], "pic.png", { type: "image/png" }));
  await user.click(screen.getByRole("button", { name: /upload asset/i }));

  expect(await screen.findByText("Uploaded")).toBeTruthy();
  const post = calls.find((call) => call.method === "POST" && call.url === "/api/assets/")!;
  expect(post.body).toBeInstanceOf(FormData);
  expect((post.body as FormData).get("workspace_id")).toBe("11");
  expect(post.headers.get("Content-Type")).toBeNull();
});

test("uploaded and generated sources remain distinct in the list and image picker", async () => {
  installFetch({
    ...baseRoutes,
    "GET /api/assets/?workspace_id=11": json([
      photo, { ...photo, id: 44, name: "Generated landscape", source: "generation" },
      { ...photo, id: 45, name: "Legacy image", source: "unknown" },
    ]),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  await screen.findByText("Hero photo");
  expect(screen.getByText(/image · Uploaded/)).toBeTruthy();
  expect(screen.getByText(/image · Generated/)).toBeTruthy();
  expect(screen.getByText(/image · Source unknown/)).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Scene kind"), "image");
  expect(screen.getByRole("option", { name: "Hero photo — Uploaded" })).toBeTruthy();
  expect(screen.getByRole("option", { name: "Generated landscape — Generated" })).toBeTruthy();
  expect(screen.getByRole("option", { name: "Legacy image — Source unknown" })).toBeTruthy();
});

test("upload, image scene and export work end to end", async () => {
  const { calls } = installFetch({
    ...baseRoutes,
    "POST /api/assets/": json({ ...photo, id: 43, name: "My image" }, 201),
    "POST /api/projects/5/scenes/": json({ id: 2, project_id: 5, kind: "image", title: "Uploaded scene", config: { asset_id: 43 } }, 201),
    "POST /api/projects/5/exports/": json(exportRecord, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  await screen.findByText("Hero photo");
  await user.upload(screen.getByLabelText("Upload media"), new File(["fixture"], "my-image.png", { type: "image/png" }));
  await user.click(screen.getByRole("button", { name: "Upload asset" }));
  await screen.findByText("My image");
  await user.type(screen.getByLabelText("Scene title"), "Uploaded scene");
  await user.selectOptions(screen.getByLabelText("Scene kind"), "image");
  await user.selectOptions(screen.getByLabelText("Media asset"), "43");
  await user.click(screen.getByRole("button", { name: "Add scene" }));
  await user.click(screen.getByRole("link", { name: "Go to export" }));
  await user.click(await screen.findByRole("button", { name: "Queue export" }));
  expect(await screen.findByText("Export status: queued")).toBeTruthy();
  const scene = calls.find(call => call.method === "POST" && call.url === "/api/projects/5/scenes/")!;
  expect(JSON.parse(String(scene.body)).config.asset_id).toBe(43);
});

test("image scenes require a picked asset, omit blank duration, and send asset_id", async () => {
  const { calls } = installFetch({
    ...baseRoutes,
    "POST /api/projects/5/scenes/": json({ id: 2, project_id: 5, order_index: 1, kind: "image", title: "Hero", script_text: "", config: {} }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  await user.type(await screen.findByLabelText("Scene title"), "Hero");
  await user.selectOptions(screen.getByLabelText("Scene kind"), "image");
  const add = screen.getByRole("button", { name: /add scene/i }) as HTMLButtonElement;
  expect(add.disabled).toBe(true);
  await user.selectOptions(await screen.findByLabelText("Media asset"), "42");
  await user.clear(screen.getByLabelText(/duration/i));
  expect(add.disabled).toBe(false);
  await user.click(add);

  expect(await screen.findByText("Hero")).toBeTruthy();
  const post = calls.find((call) => call.method === "POST" && call.url.endsWith("/scenes/"))!;
  expect(JSON.parse(String(post.body)).config).toEqual({ asset_id: 42 });
});

test("creates a caption track for a project without one", async () => {
  const { calls } = installFetch({
    ...csrf,
    "GET /api/projects/5/": json({ ...project, captions: [] }),
    "GET /api/assets/?workspace_id=11": json([]),
    "POST /api/projects/5/captions/": json({ ...caption, segments: [] }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  await user.click(await screen.findByRole("button", { name: /create caption track/i }));

  expect(await screen.findByRole("button", { name: /save captions/i })).toBeTruthy();
  const post = calls.find((call) => call.method === "POST" && call.url.endsWith("/captions/"))!;
  expect(JSON.parse(String(post.body))).toMatchObject({ language: "en", segments: [] });
});

test("saves edited caption segments via PATCH", async () => {
  const { calls } = installFetch({
    ...baseRoutes,
    "PATCH /api/captions/9/": json({ ...caption, segments: [{ start: 0, end: 2, text: "Hi there" }] }),
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

test("export page loads the project, requires a caption track choice, and sends it", async () => {
  const { calls } = installFetch({
    ...csrf,
    "GET /api/projects/5/": json({ ...project, captions: [caption, { ...caption, id: 10, language: "fr" }] }),
    "POST /api/projects/5/exports/": json(exportRecord, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/export");

  const queue = (await screen.findByRole("button", { name: /queue export/i })) as HTMLButtonElement;
  expect(queue.disabled).toBe(true);
  await user.selectOptions(screen.getByLabelText("Caption track"), "10");
  await user.click(queue);

  expect(await screen.findByText("Export status: queued")).toBeTruthy();
  expect(screen.queryByText(/download video/i)).toBeNull();
  const post = calls.find((c) => c.method === "POST" && c.url.includes("exports"))!;
  expect(JSON.parse(String(post.body))).toEqual({ burn_captions: true, caption_track_id: 10 });
});

test("export page warns about scenes without media before queuing", async () => {
  installFetch(baseRoutes);
  renderAt("/app/projects/5/export");
  expect(await screen.findByText(/not ready to export/i)).toBeTruthy();
  expect(screen.getByText(/Scene 1 \(script\) has no media attached/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Fix in studio" })).toBeTruthy();
});

test("export page omits the track when the project has at most one", async () => {
  const { calls } = installFetch({
    ...csrf,
    "GET /api/projects/5/": json(project),
    "POST /api/projects/5/exports/": json(exportRecord, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/export");

  await user.click(await screen.findByRole("button", { name: /queue export/i }));
  await screen.findByText("Export status: queued");
  expect(JSON.parse(String(calls.find((c) => c.method === "POST" && c.url.includes("exports"))!.body))).toEqual({ burn_captions: true });
});


test("viewers get a read-only studio and export", async () => {
  const viewer = { ...studio, role: "viewer" };
  installFetch({
    ...baseRoutes,
    "GET /api/auth/session/": json({ authenticated: true, user: owner, workspaces: [viewer] }),
  });
  renderAt("/app/projects/5/studio");

  expect((await screen.findAllByText(/read-only access to this project/i)).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /add scene/i })).toBeNull();
  expect(screen.queryByRole("button", { name: /upload asset/i })).toBeNull();
  expect(screen.queryByRole("button", { name: /create caption track/i })).toBeNull();
});

test("an expired session on the studio redirects to sign in", async () => {
  installFetch({ "GET /api/auth/session/": json({ authenticated: false, user: null, workspaces: [] }) });
  renderAt("/app/projects/5/studio");
  expect(await screen.findByRole("button", { name: /sign in/i })).toBeTruthy();
});

test("a 401 while loading the project re-verifies the session and redirects", async () => {
  installFetch({
    "GET /api/auth/session/": [
      json({ authenticated: true, user: owner, workspaces: [studio] }),
      json({ authenticated: false, user: null, workspaces: [] }),
    ],
    "GET /api/projects/5/": json({ code: "not_authenticated", message: "Expired", errors: {} }, 401),
  });
  renderAt("/app/projects/5/export");
  expect(await screen.findByRole("button", { name: /sign in/i })).toBeTruthy();
});
