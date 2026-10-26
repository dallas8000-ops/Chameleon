import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createAppRouter } from "../app/router";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const session = (role: string) => ({
  "GET /api/auth/csrf/": json({ csrfToken: "t" }),
  "GET /api/auth/session/": json({
    authenticated: true, user: { id: 1, email: "o@example.com" }, workspaces: [{ id: 11, name: "Studio", slug: "studio", role }],
  }),
});
const project = {
  id: 31, workspace_id: 11, title: "Episode 1", format: "9:16", status: "draft", ai_disclosure: true,
  created_at: "", updated_at: "", scenes: [], captions: [],
};

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

test("asks for the basics, then creates the project and moves to the script step", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "POST /api/projects/": json(project, 201),
    "GET /api/projects/31/": json(project),
  });
  const user = userEvent.setup();
  renderAt("/app/auto");

  const title = await screen.findByLabelText("What is the video called?");
  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain("Basics");
  const next = screen.getByRole("button", { name: "Continue to script" });

  await user.type(title, "Episode 1");
  expect(next.hasAttribute("disabled")).toBe(true);
  await user.click(screen.getByLabelText("Yes"));
  expect(next.hasAttribute("disabled")).toBe(false);
  await user.click(next);

  expect(await screen.findByRole("heading", { name: "Step 2: Script" })).toBeTruthy();
  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain("Script");
  expect(screen.getByText(/AI-generated people: yes/)).toBeTruthy();

  const create = calls.find((call) => call.method === "POST" && call.url === "/api/projects/");
  expect(JSON.parse(String(create?.body))).toEqual({ workspace_id: 11, title: "Episode 1", format: "9:16", ai_disclosure: true });
});

const preview = {
  characters: [{ name: "Ada Quinn", role: "Keeper", description: "", face_prompt: "x", negative_prompt: "", exists: false }],
  episodes: [
    { number: 1, title: "The Light Goes Out", scene_count: 2, over_export_limit: false, scenes: [
      { title: "Hook", role: "hook", speaker: "", character: null, text: "t" },
      { title: "Ada line", role: "line", speaker: "ADA", character: "Ada Quinn", text: "u" },
    ] },
    { number: 2, title: "Ferry Day", scene_count: 1, over_export_limit: false, scenes: [
      { title: "Ferry", role: "line", speaker: "", character: null, text: "v" },
    ] },
  ],
  warnings: [],
};
const withScenes = { ...project, scenes: [{ id: 1, project_id: 31, order_index: 0, kind: "script", title: "Ferry", script_text: "v", config: {} }] };

test("script step finds the scenes, lets you pick the episode, and adds them to this project", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/projects/31/": [json(project), json(withScenes)],
    "GET /api/characters/?workspace_id=11": json([]),
    "POST /api/projects/import-script/": [json(preview), json({ projects: [{ id: 31, title: "Episode 1", scene_count: 1 }], characters_created: [] }, 201)],
  });
  const user = userEvent.setup();
  renderAt("/app/auto/31");

  await user.type(await screen.findByLabelText("Paste your script"), "### Ep 1");
  await user.click(screen.getByRole("button", { name: "Find scenes" }));
  expect(await screen.findByText(/Ep 1: The Light Goes Out · 2 scenes/)).toBeTruthy();
  expect(screen.getByText(/Ada Quinn/)).toBeTruthy();

  await user.click(screen.getByLabelText(/Ep 2: Ferry Day/));
  await user.click(screen.getByRole("button", { name: "Add 1 scene and continue" }));

  expect(await screen.findByRole("heading", { name: "Step 3: Characters" })).toBeTruthy();
  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain("Characters");
  const [dry, real] = calls.filter((call) => call.method === "POST" && call.url === "/api/projects/import-script/");
  expect(JSON.parse(String(dry.body))).toMatchObject({ workspace_id: 11, dry_run: true, format: "9:16" });
  expect(JSON.parse(String(real.body))).toMatchObject({ dry_run: false, episodes: [2], project_id: 31, create_characters: true });
});

test("a project that already has scenes resumes past the script step", async () => {
  installFetch({ ...session("owner"), "GET /api/projects/31/": json(withScenes), "GET /api/characters/?workspace_id=11": json([]) });
  renderAt("/app/auto/31");
  expect(await screen.findByRole("heading", { name: "Step 3: Characters" })).toBeTruthy();
  expect(screen.queryByLabelText("Paste your script")).toBeNull();
  expect(screen.getByText(/· 1 scene$/)).toBeTruthy();
});

const ada = {
  id: 5, workspace_id: 11, name: "Ada Quinn", role: "Keeper", description: "", face_prompt: "x", negative_prompt: "",
  voice_notes: "", reference_asset_id: null, created_at: "", updated_at: "",
};
const bo = { ...ada, id: 6, name: "Bo", role: "Captain", reference_asset_id: 70, voice_notes: "gravelly" };
const cast = {
  ...project,
  scenes: [
    { id: 1, project_id: 31, order_index: 0, kind: "script", title: "Ada line", script_text: "a", config: { speaker: "ADA" }, character_id: 5 },
    { id: 2, project_id: 31, order_index: 1, kind: "script", title: "Bo line", script_text: "b", config: { speaker: "BO" }, character_id: 6 },
    { id: 3, project_id: 31, order_index: 2, kind: "script", title: "Armand", script_text: "c", config: { speaker: "ARMAND" }, character_id: null },
  ],
};

test("characters step asks only for what is missing, then opens the build step", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/projects/31/": json(cast),
    "GET /api/characters/?workspace_id=11": json([ada, bo, { ...ada, id: 9, name: "Not in this video" }]),
    "POST /api/assets/": json({ id: 71, workspace_id: 11, asset_type: "image", name: "ada.png", content_type: "image/png", size_bytes: 1, created_at: "" }, 201),
    "PATCH /api/characters/5/": [json({ ...ada, reference_asset_id: 71 }), json({ ...ada, reference_asset_id: 71, voice_notes: "calm" })],
  });
  const user = userEvent.setup();
  renderAt("/app/auto/31");

  expect(await screen.findByText("Image needed")).toBeTruthy();
  expect(screen.queryByText("Not in this video")).toBeNull();
  expect(screen.getByText(/not linked to a character: ARMAND/)).toBeTruthy();
  expect(screen.getByLabelText("Replace reference image for Bo")).toBeTruthy();
  const next = screen.getByRole("button", { name: "Add 1 more reference image to continue" });
  expect(next.hasAttribute("disabled")).toBe(true);

  await user.upload(screen.getByLabelText("Reference image for Ada Quinn"), new File(["x"], "ada.png", { type: "image/png" }));
  const ready = await screen.findByRole("button", { name: "Continue to build" });
  expect(screen.queryByText("Image needed")).toBeNull();

  await user.type(screen.getByLabelText("Voice notes for Ada Quinn (optional)"), "calm");
  await user.click(screen.getByRole("button", { name: "Save voice notes" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Save voice notes" })).toBeNull());
  await user.click(ready);

  expect(await screen.findByRole("heading", { name: "Step 4: Build" })).toBeTruthy();
  const patches = calls.filter((call) => call.method === "PATCH");
  expect(patches.map((call) => JSON.parse(String(call.body)))).toEqual([{ reference_asset_id: 71 }, { voice_notes: "calm" }]);
});

test("shows the server's message when the project cannot be created", async () => {
  installFetch({
    ...session("owner"),
    "POST /api/projects/": json({ code: "validation_error", message: "Invalid request.", errors: { title: ["Too long."] } }, 400),
  });
  const user = userEvent.setup();
  renderAt("/app/auto");
  await user.type(await screen.findByLabelText("What is the video called?"), "x");
  await user.click(screen.getByLabelText("No"));
  await user.click(screen.getByRole("button", { name: "Continue to script" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Too long.");
});

test("viewers cannot start a project", async () => {
  installFetch(session("viewer"));
  renderAt("/app/auto");
  expect(await screen.findByText(/read-only access/i)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Continue to script" })).toBeNull();
});
