import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createAppRouter } from "../app/router";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const scene = { id: 1, project_id: 5, order_index: 0, kind: "script", title: "Shot", script_text: "", config: { role: "dialogue" }, character_id: null };
const project = (extra = {}) => ({
  id: 5, workspace_id: 11, title: "Ep 1", format: "9:16", status: "draft", ai_disclosure: false, created_at: "x", updated_at: "x",
  scenes: [scene], captions: [], ...extra,
});
const asset = (id: number, type: string, name: string) => ({ id, workspace_id: 11, asset_type: type, source: "upload", name, content_type: "x", size_bytes: 1, created_at: "x" });
const assets = [asset(1, "video", "broll.mp4"), asset(2, "image", "still.png"), asset(3, "audio", "kato-line.wav")];
const session = (role = "owner") => ({
  "GET /api/auth/csrf/": json({ csrfToken: "t" }),
  "GET /api/auth/session/": json({
    authenticated: true, user: { id: 1, email: "o@example.com" }, workspaces: [{ id: 11, name: "Studio", slug: "studio", role }],
  }),
});
const studioRoutes = (projectBody = project()) => ({
  ...session(),
  "GET /api/projects/5/": json(projectBody),
  "GET /api/assets/?workspace_id=11": json(assets),
  "GET /api/characters/?workspace_id=11": json([]),
});

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

test("a video scene saves its media, trim, voice track and text overlay", async () => {
  const { calls } = installFetch({
    ...studioRoutes(),
    "PATCH /api/scenes/1/": json({ ...scene, kind: "video", config: { role: "dialogue", asset_id: 1 } }),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  await user.selectOptions(await screen.findByLabelText("Scene type"), "video");
  await user.selectOptions(screen.getByLabelText("Media for this scene"), "1");
  await user.type(screen.getByLabelText("Trim start (seconds)"), "1.5");
  await user.type(screen.getByLabelText("Trim end (seconds)"), "4");
  await user.selectOptions(screen.getByLabelText("Voice track audio"), "3");
  await user.type(screen.getByLabelText("Voice volume (%)"), "80");
  await user.click(screen.getByRole("button", { name: "Add text overlay" }));
  await user.type(screen.getByLabelText("Overlay 1 text"), "Hook line");
  await user.selectOptions(screen.getByLabelText("Overlay 1 position"), "top");
  await user.click(screen.getByRole("button", { name: "Save scene" }));
  expect(await screen.findByText("Scene saved.")).toBeTruthy();

  const patch = calls.find((call) => call.method === "PATCH" && call.url === "/api/scenes/1/")!;
  const body = JSON.parse(String(patch.body));
  expect(body.kind).toBe("video");
  expect(body.config).toMatchObject({
    role: "dialogue", asset_id: 1, trim_start: 1.5, trim_end: 4, audio_asset_id: 3, audio_volume: 0.8,
    overlays: [{ text: "Hook line", start: 0, end: 2, position: "top", size: "medium" }],
  });
});

test("an image scene can match its length to the voice track, which needs a voice track first", async () => {
  installFetch(studioRoutes(project({ scenes: [{ ...scene, kind: "image", config: { asset_id: 2 } }] })));
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  const match = (await screen.findByLabelText("Match the voice track length")) as HTMLInputElement;
  expect(match.disabled).toBe(true);
  await user.selectOptions(screen.getByLabelText("Voice track audio"), "3");
  expect((screen.getByLabelText("Match the voice track length") as HTMLInputElement).disabled).toBe(false);
  expect(screen.getByLabelText("Show for (seconds)")).toBeTruthy();
});

test("an empty text overlay blocks saving until it is filled in or removed", async () => {
  installFetch(studioRoutes());
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  await user.click(await screen.findByRole("button", { name: "Add text overlay" }));
  expect((screen.getByRole("button", { name: "Save scene" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/empty text overlay/i)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Remove overlay 1" }));
  expect((screen.getByRole("button", { name: "Save scene" }) as HTMLButtonElement).disabled).toBe(false);
});

test("the AI disclosure setting is saved from the studio", async () => {
  const { calls } = installFetch({
    ...studioRoutes(),
    "PATCH /api/projects/5/": json({ id: 5, workspace_id: 11, title: "Ep 1", format: "9:16", status: "draft", ai_disclosure: true, created_at: "x", updated_at: "x" }),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  const toggle = (await screen.findByLabelText("This project contains AI-generated people")) as HTMLInputElement;
  expect(toggle.checked).toBe(false);
  await user.click(toggle);
  expect(((await screen.findByLabelText("This project contains AI-generated people")) as HTMLInputElement).checked).toBe(true);
  const patch = calls.find((call) => call.method === "PATCH" && call.url === "/api/projects/5/")!;
  expect(JSON.parse(String(patch.body))).toEqual({ ai_disclosure: true });
});

test("the export page shows the posting checklist and sends the AI label choice only when asked", async () => {
  const withMedia = project({ ai_disclosure: true, scenes: [{ ...scene, kind: "image", config: { asset_id: 2 } }] });
  const { calls } = installFetch({
    ...session(),
    "GET /api/projects/5/": json(withMedia),
    "POST /api/projects/5/exports/": json({ id: 9, project_id: 5, status: "queued", format: "9:16", settings: {}, error_code: "", error_message: "", video_available: false, subtitles_available: false, created_at: "", updated_at: "" }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/export");
  expect(await screen.findByText("Before you post: AI disclosure")).toBeTruthy();
  expect(screen.getByText("AI-generated character")).toBeTruthy();
  await user.click(screen.getByLabelText(/Add a small AI-generated label/));
  await user.click(screen.getByRole("button", { name: "Queue export" }));
  await screen.findByText("Export status: queued");
  const post = calls.find((call) => call.method === "POST" && call.url === "/api/projects/5/exports/")!;
  expect(JSON.parse(String(post.body))).toEqual({ burn_captions: true, burn_ai_label: true });
});

test("projects without the AI setting show no checklist or label option", async () => {
  installFetch({
    ...session(),
    "GET /api/projects/5/": json(project({ scenes: [{ ...scene, kind: "image", config: { asset_id: 2 } }] })),
  });
  renderAt("/app/projects/5/export");
  await screen.findByRole("button", { name: "Queue export" });
  expect(screen.queryByText("Before you post: AI disclosure")).toBeNull();
  expect(screen.queryByLabelText(/AI-generated label/)).toBeNull();
});
