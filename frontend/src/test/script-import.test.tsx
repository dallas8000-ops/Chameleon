import React from "react";
import { render, screen } from "@testing-library/react";
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
const preview = {
  characters: [
    { name: "Ada Quinn", role: "Lighthouse keeper", description: "", face_prompt: "x", negative_prompt: "", exists: false },
    { name: "Bo", role: "Ferry captain", description: "", face_prompt: "y", negative_prompt: "", exists: true },
  ],
  episodes: [
    { number: 1, title: "The Light Goes Out", scene_count: 8, over_export_limit: false, scenes: [{ title: "Hook", role: "hook", speaker: "", character: null, text: "t" }] },
    { number: 2, title: "Ferry Day", scene_count: 25, over_export_limit: true, scenes: [] },
  ],
  warnings: ["Episode 2 has 25 scenes; export supports at most 20."],
};

function renderImport() {
  return render(<RouterProvider router={createAppRouter(["/app/import"])} />);
}

beforeEach(() => {
  clearCsrfToken();
  resetSessionStore();
  sessionStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("previews a script, then imports the selected episodes", async () => {
  const { calls } = installFetch({
    ...session("owner"),
    "POST /api/projects/import-script/": [
      json(preview),
      json({ projects: [{ id: 21, title: "Ep 1: The Light Goes Out", scene_count: 8 }], characters_created: ["Ada Quinn"] }, 201),
    ],
  });
  const user = userEvent.setup();
  renderImport();

  await user.type(await screen.findByLabelText("Script"), "### Ep 1");
  await user.click(screen.getByRole("button", { name: "Preview import" }));
  expect(await screen.findByText("Check before importing")).toBeTruthy();
  expect(screen.getByText("Already in library")).toBeTruthy();
  expect(screen.getByText("Over the 20-scene export limit")).toBeTruthy();

  await user.click(screen.getByLabelText("Import episode 2"));
  await user.click(screen.getByRole("button", { name: "Import 1 episode" }));
  expect(await screen.findByText("Imported 1 project")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Ep 1: The Light Goes Out" }).getAttribute("href")).toBe("/app/projects/21/studio");
  expect(screen.getByText(/New characters: Ada Quinn/)).toBeTruthy();

  const [first, second] = calls.filter((call) => call.method === "POST" && call.url === "/api/projects/import-script/");
  expect(JSON.parse(String(first.body))).toMatchObject({ workspace_id: 11, dry_run: true, format: "9:16" });
  expect(JSON.parse(String(second.body))).toMatchObject({ dry_run: false, episodes: [1], create_characters: true });
});

test("shows the server's message when the script has no episodes", async () => {
  installFetch({
    ...session("owner"),
    "POST /api/projects/import-script/": json(
      { code: "validation_error", message: "Invalid request.", errors: { script: ["No episodes found."] } }, 400,
    ),
  });
  const user = userEvent.setup();
  renderImport();
  await user.type(await screen.findByLabelText("Script"), "hello");
  await user.click(screen.getByRole("button", { name: "Preview import" }));
  expect((await screen.findByRole("alert")).textContent).toContain("No episodes found.");
  expect(screen.queryByRole("button", { name: /^Import \d/ })).toBeNull();
});

test("viewers cannot import", async () => {
  installFetch(session("reviewer"));
  renderImport();
  expect(await screen.findByText(/read-only access/i)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Preview import" })).toBeNull();
});
