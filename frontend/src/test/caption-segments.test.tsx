import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CaptionEditor } from "../features/studio/CaptionEditor";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const track = (segments: { start: number; end: number; text: string }[]) =>
  ({ id: 9, project_id: 5, language: "en", segments, style: {}, updated_at: "x" });
const csrf = { "GET /api/auth/csrf/": json({ csrfToken: "t" }) };

beforeEach(() => {
  clearCsrfToken();
  resetSessionStore();
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("an empty track offers an add-segment control that starts at zero", async () => {
  const user = userEvent.setup();
  render(<CaptionEditor caption={track([])} onSaved={() => {}} />);
  await user.click(screen.getByRole("button", { name: /add segment/i }));
  expect((screen.getByLabelText("Segment 1 start") as HTMLInputElement).value).toBe("0");
  expect((screen.getByLabelText("Segment 1 end") as HTMLInputElement).value).toBe("2");
});

test("new segments continue after the previous end and can be removed", async () => {
  const user = userEvent.setup();
  render(<CaptionEditor caption={track([{ start: 0, end: 1.5, text: "One" }])} onSaved={() => {}} />);
  await user.click(screen.getByRole("button", { name: /add segment/i }));
  expect((screen.getByLabelText("Segment 2 start") as HTMLInputElement).value).toBe("1.5");
  await user.click(screen.getByRole("button", { name: /remove segment 2/i }));
  expect(screen.queryByLabelText("Segment 2 text")).toBeNull();
  expect(screen.getByLabelText("Segment 1 text")).toBeTruthy();
});

test("invalid segments are rejected locally and nothing is sent", async () => {
  const { calls } = installFetch(csrf);
  const user = userEvent.setup();
  render(<CaptionEditor caption={track([])} onSaved={() => {}} />);
  await user.click(screen.getByRole("button", { name: /add segment/i }));
  await user.click(screen.getByRole("button", { name: /save captions/i }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/segment 1.*text/i);

  await user.type(screen.getByLabelText("Segment 1 text"), "Hi");
  await user.clear(screen.getByLabelText("Segment 1 end"));
  await user.type(screen.getByLabelText("Segment 1 end"), "0");
  await user.click(screen.getByRole("button", { name: /save captions/i }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/segment 1.*end.*after.*start/i);
  expect(calls.some((c) => c.method === "PATCH")).toBe(false);
});

test("overlapping segments are rejected locally", async () => {
  const { calls } = installFetch(csrf);
  const user = userEvent.setup();
  render(<CaptionEditor caption={track([{ start: 0, end: 2, text: "A" }, { start: 1, end: 3, text: "B" }])} onSaved={() => {}} />);
  await user.click(screen.getByRole("button", { name: /save captions/i }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/segment 2.*overlap/i);
  expect(calls.some((c) => c.method === "PATCH")).toBe(false);
});

test("a valid added segment is saved and controls are pending while saving", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const saved = track([{ start: 0, end: 2, text: "Hi" }]);
  const { calls } = installFetch({
    ...csrf,
    "PATCH /api/captions/9/": async () => { await gate; return json(saved); },
  } as never);
  const user = userEvent.setup();
  const onSaved = vi.fn();
  render(<CaptionEditor caption={track([])} onSaved={onSaved} />);
  await user.click(screen.getByRole("button", { name: /add segment/i }));
  await user.type(screen.getByLabelText("Segment 1 text"), "Hi");
  await user.click(screen.getByRole("button", { name: /save captions/i }));
  expect((screen.getByRole("button", { name: /save captions/i }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: /add segment/i }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: /remove segment 1/i }) as HTMLButtonElement).disabled).toBe(true);
  release();
  expect(await screen.findByText("Captions saved.")).toBeTruthy();
  expect(JSON.parse(String(calls.find((c) => c.method === "PATCH")!.body))).toEqual({ segments: saved.segments });
  expect(onSaved).toHaveBeenCalled();
});

test("read-only viewers get no add or remove controls", () => {
  render(<CaptionEditor caption={track([{ start: 0, end: 2, text: "A" }])} canWrite={false} onSaved={() => {}} />);
  expect(screen.queryByRole("button", { name: /add segment/i })).toBeNull();
  expect(screen.queryByRole("button", { name: /remove segment/i })).toBeNull();
  expect((screen.getByLabelText("Segment 1 text") as HTMLInputElement).disabled).toBe(true);
});


