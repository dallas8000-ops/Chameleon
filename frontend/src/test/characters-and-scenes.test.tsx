import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createAppRouter } from "../app/router";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const scenes = [
  { id: 1, project_id: 5, order_index: 0, kind: "script", title: "Hook", script_text: "Stop scrolling.", config: {}, character_id: null },
  { id: 2, project_id: 5, order_index: 1, kind: "script", title: "Reality", script_text: "", config: {}, character_id: null },
];
const project = {
  id: 5, workspace_id: 11, title: "Ep 1", format: "9:16", status: "draft", created_at: "x", updated_at: "x", scenes, captions: [],
};
const photo = { id: 42, workspace_id: 11, asset_type: "image", source: "upload", name: "Kato face", content_type: "image/png", size_bytes: 10, created_at: "x" };
const kato = {
  id: 7, workspace_id: 11, name: "Kato", role: "Boda boda rider", description: "", face_prompt: "Ugandan man", negative_prompt: "cartoon",
  voice_notes: "", reference_asset_id: 42, created_at: "x", updated_at: "x",
};
const session = (role: string) => ({
  "GET /api/auth/csrf/": json({ csrfToken: "t" }),
  "GET /api/auth/session/": json({
    authenticated: true, user: { id: 1, email: "o@example.com" }, workspaces: [{ id: 11, name: "Studio", slug: "studio", role }],
  }),
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

test("the character library lists characters with their reference image", async () => {
  installFetch({
    ...session("owner"),
    "GET /api/characters/?workspace_id=11": json([kato]),
    "GET /api/assets/?workspace_id=11": json([photo]),
  });
  renderAt("/app/characters");
  const list = await screen.findByRole("list");
  expect(within(list).getByText("Kato")).toBeTruthy();
  expect(within(list).getByText("Boda boda rider")).toBeTruthy();
  expect(list.querySelector("img")?.getAttribute("src")).toBe("/api/assets/42/content/");
});

test("creates a character with a reference image", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/characters/?workspace_id=11": json([]),
    "GET /api/assets/?workspace_id=11": json([photo]),
    "POST /api/characters/": json({ ...kato, id: 8, name: "Mama Grace", role: "Landlady" }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/characters");
  await screen.findByText("No characters yet.");
  await user.type(screen.getByLabelText("Name"), "Mama Grace");
  await user.type(screen.getByLabelText("Role"), "Landlady");
  await user.selectOptions(screen.getByLabelText("Reference image"), "42");
  await user.click(screen.getByRole("button", { name: "Create character" }));
  expect(await screen.findByRole("heading", { name: "Edit character" })).toBeTruthy();
  const post = calls.find((call) => call.method === "POST" && call.url === "/api/characters/")!;
  expect(JSON.parse(String(post.body))).toMatchObject({ workspace_id: 11, name: "Mama Grace", role: "Landlady", reference_asset_id: 42 });
});

test("viewers can browse characters but not change them", async () => {
  installFetch({
    ...session("reviewer"),
    "GET /api/characters/?workspace_id=11": json([kato]),
    "GET /api/assets/?workspace_id=11": json([photo]),
  });
  renderAt("/app/characters");
  await screen.findByText("Kato");
  expect(screen.queryByRole("button", { name: /create character/i })).toBeNull();
  expect(screen.getByText(/read-only access/i)).toBeTruthy();
});

test("a scene can be created with a character", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/projects/5/": json(project),
    "GET /api/assets/?workspace_id=11": json([photo]),
    "GET /api/characters/?workspace_id=11": json([kato]),
    "POST /api/projects/5/scenes/": json({ ...scenes[0], id: 3, title: "Arrival", character_id: 7 }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");
  await user.type(await screen.findByLabelText("Scene title"), "Arrival");
  await user.selectOptions(screen.getByLabelText("Character"), "7");
  await user.click(screen.getByRole("button", { name: "Add scene" }));
  expect(await screen.findByText(/script · Kato/)).toBeTruthy();
  const post = calls.find((call) => call.method === "POST" && call.url === "/api/projects/5/scenes/")!;
  expect(JSON.parse(String(post.body)).character_id).toBe(7);
});

test("the selected scene can be edited, moved and deleted", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/projects/5/": json(project),
    "GET /api/assets/?workspace_id=11": json([]),
    "GET /api/characters/?workspace_id=11": json([kato]),
    "PATCH /api/scenes/2/": [json({ ...scenes[1], title: "Reality check" }), json({ ...scenes[1], order_index: 0 })],
    "DELETE /api/scenes/2/": new Response(null, { status: 204 }),
  });
  const user = userEvent.setup();
  renderAt("/app/projects/5/studio");

  const title = await screen.findByLabelText("Rename this scene");
  await user.clear(title);
  await user.type(title, "Reality check");
  await user.click(screen.getByRole("button", { name: "Save scene" }));
  expect(await screen.findByText("Scene saved.")).toBeTruthy();
  expect(await screen.findByText("Reality check")).toBeTruthy();

  expect((screen.getByRole("button", { name: "Move later" }) as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole("button", { name: "Move earlier" }));
  await screen.findByRole("heading", { name: "Scene 1 details" });
  expect(JSON.parse(String(calls.filter((c) => c.method === "PATCH")[1].body))).toEqual({ order_index: 0 });

  await user.click(screen.getByRole("button", { name: "Delete scene" }));
  await user.click(screen.getByRole("button", { name: "Confirm delete scene" }));
  expect(await screen.findByRole("heading", { name: "Scene 1 details" })).toBeTruthy();
  expect(screen.queryByText("Reality check")).toBeNull();
  expect(calls.some((call) => call.method === "DELETE" && call.url === "/api/scenes/2/")).toBe(true);
});

test("viewers see no scene editing controls", async () => {
  installFetch({
    ...session("reviewer"),
    "GET /api/projects/5/": json(project),
    "GET /api/assets/?workspace_id=11": json([]),
    "GET /api/characters/?workspace_id=11": json([]),
  });
  renderAt("/app/projects/5/studio");
  await screen.findByRole("heading", { name: /studio: ep 1/i });
  expect(screen.queryByRole("button", { name: "Delete scene" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Save scene" })).toBeNull();
});
