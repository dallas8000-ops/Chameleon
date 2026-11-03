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

function capabilities(configured: boolean) {
  return {
    configured,
    missing: configured ? [] : ["RUNPOD_API_KEY"],
    capabilities: [{ capability: "text_to_image", label: "Picture", description: "", available: configured }],
  };
}

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
    "GET /api/generation/capabilities/?workspace_id=11": json(capabilities(true)),
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

const ready = {
  ...project,
  scenes: [
    { id: 1, project_id: 31, order_index: 0, kind: "image", title: "Hook", script_text: "a", config: { asset_id: 80 }, character_id: null },
    { id: 2, project_id: 31, order_index: 1, kind: "script", title: "Bo line", script_text: "Ferry leaves at noon", config: { speaker: "BO", location: "harbour" }, character_id: 6 },
  ],
};
const job = { id: 501, workspace_id: 11, project_id: 31, scene_id: 2, capability: "text_to_image", label: "Picture", result_asset_id: null, error_code: "", error_message: "", created_at: "", finished_at: null };

test("build makes the missing pictures on the GPU, then export renders the video", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/projects/31/": json(ready),
    "GET /api/characters/?workspace_id=11": json([bo]),
    "GET /api/generation/capabilities/?workspace_id=11": json(capabilities(true)),
    "POST /api/generation/jobs/": json({ ...job, status: "submitted" }, 202),
    "GET /api/generation/jobs/501/": json({ ...job, status: "completed", result_asset_id: 81 }),
    "PATCH /api/scenes/2/": json({ ...ready.scenes[1], kind: "image", config: { ...ready.scenes[1].config, asset_id: 81 } }),
    "POST /api/projects/31/exports/": json({
      id: 9, project_id: 31, status: "completed", format: "9:16", settings: {}, error_code: "", error_message: "",
      video_available: true, subtitles_available: false, created_at: "", updated_at: "",
    }, 201),
  });
  const user = userEvent.setup();
  renderAt("/app/auto/31");

  await user.click(await screen.findByRole("button", { name: "Continue to build" }));
  expect(await screen.findByRole("heading", { name: "Step 4: Build" })).toBeTruthy();
  expect(screen.getByText("Needs a picture")).toBeTruthy();
  await user.click(await screen.findByRole("button", { name: "Make 1 picture" }));
  const next = await screen.findByRole("button", { name: "Continue to export" }, { timeout: 8000 });

  const create = calls.find((call) => call.method === "POST" && call.url === "/api/generation/jobs/");
  const body = JSON.parse(String(create?.body));
  expect(body).toMatchObject({ workspace_id: 11, capability: "text_to_image", project_id: 31, scene_id: 2, params: { size: "portrait" } });
  expect(body.params.prompt).toMatch(/^x\. harbour\. Ferry leaves at noon\. cinematic/);
  const patch = calls.find((call) => call.method === "PATCH" && call.url === "/api/scenes/2/");
  expect(JSON.parse(String(patch?.body))).toEqual({ kind: "image", config: { speaker: "BO", location: "harbour", asset_id: 81 } });

  await user.click(next);
  expect(await screen.findByRole("heading", { name: "Step 5: Export" })).toBeTruthy();
  const make = screen.getByRole("button", { name: "Make the video" });
  expect(make.hasAttribute("disabled")).toBe(true);
  await user.click(screen.getByLabelText("I will label this video as AI-generated when I post it"));
  await user.click(make);
  expect(await screen.findByText("Your video is ready")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Download video" }).getAttribute("href")).toBe("/api/exports/9/video/");
  const render = calls.find((call) => call.method === "POST" && call.url === "/api/projects/31/exports/");
  expect(JSON.parse(String(render?.body))).toEqual({ burn_captions: false, burn_ai_label: true });
}, 15000);

test("characters with a voice sample get their line spoken, and the scene lasts as long as the line", async () => {
  const voiced = { ...bo, voice_sample_asset_id: 33 };
  const { calls } = installFetch({
    ...session("owner"),
    "GET /api/projects/31/": json(ready),
    "GET /api/characters/?workspace_id=11": json([voiced]),
    "GET /api/generation/capabilities/?workspace_id=11": json({
      configured: true, missing: [],
      capabilities: [
        { capability: "text_to_image", label: "Picture", description: "", available: true },
        { capability: "voice", label: "Voice", description: "", available: true },
      ],
    }),
    "POST /api/generation/jobs/": [json({ ...job, status: "submitted" }, 202), json({ ...job, id: 502, capability: "voice", status: "submitted" }, 202)],
    "GET /api/generation/jobs/501/": json({ ...job, status: "completed", result_asset_id: 81 }),
    "GET /api/generation/jobs/502/": json({ ...job, id: 502, capability: "voice", status: "completed", result_asset_id: 90 }),
    "PATCH /api/scenes/2/": [
      json({ ...ready.scenes[1], kind: "image", config: { ...ready.scenes[1].config, asset_id: 81 } }),
      json({ ...ready.scenes[1], kind: "image", config: { ...ready.scenes[1].config, asset_id: 81, audio_asset_id: 90, fit_to_audio: true } }),
    ],
  });
  const user = userEvent.setup();
  renderAt("/app/auto/31");

  await user.click(await screen.findByRole("button", { name: "Continue to build" }));
  expect(await screen.findByText("Needs a picture and its voice line")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Make 1 picture and 1 voice line" }));
  expect(await screen.findByText("Ready, with voice", undefined, { timeout: 12000 })).toBeTruthy();

  const jobs = calls.filter((call) => call.method === "POST" && call.url === "/api/generation/jobs/").map((call) => JSON.parse(String(call.body)));
  expect(jobs.map((body) => body.capability)).toEqual(["text_to_image", "voice"]);
  expect(jobs[1].params).toEqual({ text: "Ferry leaves at noon", voice_sample_asset_id: 33 });
  const patches = calls.filter((call) => call.method === "PATCH" && call.url === "/api/scenes/2/").map((call) => JSON.parse(String(call.body)));
  expect(patches[1]).toEqual({ config: { speaker: "BO", location: "harbour", asset_id: 81, audio_asset_id: 90, fit_to_audio: true } });
}, 20000);

test("build explains plainly when the GPU worker is not connected", async () => {
  installFetch({
    ...session("owner"),
    "GET /api/projects/31/": json(ready),
    "GET /api/characters/?workspace_id=11": json([bo]),
    "GET /api/generation/capabilities/?workspace_id=11": json(capabilities(false)),
  });
  const user = userEvent.setup();
  renderAt("/app/auto/31");
  await user.click(await screen.findByRole("button", { name: "Continue to build" }));
  expect(await screen.findByText("Picture making is not connected.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Make 1 picture" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("link", { name: "Add my own in the studio" }).getAttribute("href")).toBe("/app/projects/31/studio");
});

test("viewers cannot start a project", async () => {
  installFetch(session("viewer"));
  renderAt("/app/auto");
  expect(await screen.findByText(/read-only access/i)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Continue to script" })).toBeNull();
});
