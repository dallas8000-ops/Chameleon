import React from "react";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { createAppRouter } from "../app/router";
import { clearCsrfToken } from "../lib/api/client";
import { resetSessionStore } from "../lib/auth/session-store";
import { installFetch, json } from "./fetch-mock";

const owner = { id: 7, email: "owner@example.com" };
const creatorStudio = { id: 11, name: "Creator Studio", slug: "creator-studio", role: "owner" };
const secondStudio = { id: 12, name: "Second Studio", slug: "second-studio", role: "editor" };
const projects = [
  { id: 1, workspace_id: 11, title: "Launch teaser", format: "vertical", status: "draft", created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-02T10:00:00Z" },
  { id: 2, workspace_id: 11, title: "Product walkthrough", format: "landscape", status: "rendering", created_at: "2026-10-03T10:00:00Z", updated_at: "2026-10-04T10:00:00Z" },
];
const anonymous = { authenticated: false, user: null, workspaces: [] };

function renderApp(path = "/") {
  return render(<RouterProvider router={createAppRouter([path])} />);
}

beforeEach(() => {
  clearCsrfToken();
  resetSessionStore();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("register flow", () => {
  test("fetches CSRF, registers, rotates CSRF, and lands on the workspace dashboard", async () => {
    const { calls } = installFetch({
      "GET /api/auth/csrf/": [json({ csrfToken: "token-1" }), json({ csrfToken: "token-2" })],
      "POST /api/auth/register/": json({ authenticated: true, user: owner, workspaces: [creatorStudio], workspace: creatorStudio }, 201),
      "GET /api/workspaces/": json([creatorStudio]),
      "GET /api/projects/?workspace_id=11": json(projects),
    });
    const user = userEvent.setup();
    renderApp("/");

    await user.click(screen.getByRole("link", { name: /get started/i }));
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "ChangeMe123!");
    await user.type(screen.getByLabelText(/workspace name/i), "Creator Studio");
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(await screen.findByRole("heading", { name: /creator studio/i, level: 1 })).toBeTruthy();
    expect(await screen.findByText("Launch teaser")).toBeTruthy();
    expect(screen.getByText("Product walkthrough")).toBeTruthy();

    const sequence = calls.map((call) => `${call.method} ${call.url}`);
    expect(sequence.slice(0, 3)).toEqual(["GET /api/auth/csrf/", "POST /api/auth/register/", "GET /api/auth/csrf/"]);
    expect(sequence).toContain("GET /api/workspaces/");
    expect(sequence).toContain("GET /api/projects/?workspace_id=11");

    const register = calls[1];
    expect(register.headers.get("X-CSRFToken")).toBe("token-1");
    expect(register.headers.get("Content-Type")).toBe("application/json");
    expect(register.credentials).toBe("same-origin");
    expect(JSON.parse(register.body as string)).toEqual({
      email: "owner@example.com",
      password: "ChangeMe123!",
      workspace_name: "Creator Studio",
    });

    for (const call of calls.filter((c) => c.method === "GET")) {
      expect(call.headers.get("Content-Type")).toBeNull();
      expect(call.headers.get("X-CSRFToken")).toBeNull();
      expect(call.credentials).toBe("same-origin");
      expect(call.url.startsWith("/api/")).toBe(true);
    }
  });

  test("renders server validation errors and keeps the user on the form", async () => {
    installFetch({
      "GET /api/auth/csrf/": json({ csrfToken: "token-1" }),
      "POST /api/auth/register/": json(
        { code: "validation_error", message: "Registration data is invalid.", errors: { email: ["A user with this email already exists."] } },
        400,
      ),
    });
    const user = userEvent.setup();
    renderApp("/register");

    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "ChangeMe123!");
    await user.type(screen.getByLabelText(/workspace name/i), "Creator Studio");
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Registration data is invalid.");
    expect(alert.textContent).toContain("A user with this email already exists.");
    const button = screen.getByRole("button", { name: /create workspace/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(screen.queryByRole("heading", { name: /creator studio/i })).toBeNull();
  });

  test("shows a pending state while the registration request is in flight", async () => {
    let finish: (response: Response) => void = () => undefined;
    installFetch({
      "GET /api/auth/csrf/": json({ csrfToken: "token-1" }),
      "POST /api/auth/register/": () => new Promise<Response>((resolve) => { finish = resolve; }),
    });
    const user = userEvent.setup();
    renderApp("/register");

    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "ChangeMe123!");
    await user.type(screen.getByLabelText(/workspace name/i), "Creator Studio");
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    const pending = (await screen.findByRole("button", { name: /creating workspace/i })) as HTMLButtonElement;
    expect(pending.disabled).toBe(true);

    await act(async () => {
      finish(json({ code: "throttled", message: "Too many attempts.", errors: {} }, 429));
    });
    expect((await screen.findByRole("alert")).textContent).toContain("Too many attempts.");
  });
});

describe("login flow", () => {
  test("logs in with CSRF, rotates the token, and opens the first workspace", async () => {
    const { calls } = installFetch({
      "GET /api/auth/csrf/": [json({ csrfToken: "token-1" }), json({ csrfToken: "token-2" })],
      "POST /api/auth/login/": json({ authenticated: true, user: owner, workspaces: [creatorStudio, secondStudio] }),
      "GET /api/workspaces/": json([creatorStudio, secondStudio]),
      "GET /api/projects/?workspace_id=11": json(projects),
    });
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("heading", { name: "Creator Studio", level: 1 })).toBeTruthy();
    expect(await screen.findByText("Launch teaser")).toBeTruthy();

    const sequence = calls.map((call) => `${call.method} ${call.url}`);
    expect(sequence.slice(0, 3)).toEqual(["GET /api/auth/csrf/", "POST /api/auth/login/", "GET /api/auth/csrf/"]);
    expect(calls[1].headers.get("X-CSRFToken")).toBe("token-1");
    expect(JSON.parse(calls[1].body as string)).toEqual({ email: "owner@example.com", password: "ChangeMe123!" });
  });

  test("renders invalid credential errors from the server", async () => {
    installFetch({
      "GET /api/auth/csrf/": json({ csrfToken: "token-1" }),
      "POST /api/auth/login/": json(
        { code: "invalid_credentials", message: "Email or password is incorrect.", errors: { non_field_errors: ["Email or password is incorrect."] } },
        400,
      ),
    });
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect((await screen.findByRole("alert")).textContent).toContain("Email or password is incorrect.");
  });

  test("renders a network error when the server cannot be reached", async () => {
    installFetch({
      "GET /api/auth/csrf/": new TypeError("Failed to fetch"),
    });
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/unable to reach the server/i);
    expect((screen.getByRole("button", { name: /sign in/i }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("dashboard", () => {
  test("bootstraps an existing session without CSRF and lists workspace projects", async () => {
    const { calls } = installFetch({
      "GET /api/auth/session/": json({ authenticated: true, user: owner, workspaces: [creatorStudio] }),
      "GET /api/workspaces/": json([creatorStudio]),
      "GET /api/projects/?workspace_id=11": json(projects),
    });
    renderApp("/app");

    expect(await screen.findByRole("heading", { name: "Creator Studio", level: 1 })).toBeTruthy();
    const list = await screen.findByRole("list", { name: /projects/i });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Launch teaser")).toBeTruthy();
    expect(calls.some((call) => call.url === "/api/auth/csrf/")).toBe(false);
  });

  test("redirects anonymous visitors to sign in", async () => {
    installFetch({ "GET /api/auth/session/": json(anonymous) });
    renderApp("/app");

    expect(await screen.findByRole("button", { name: /sign in/i })).toBeTruthy();
  });

  test("shows an empty state when the workspace has no projects", async () => {
    installFetch({
      "GET /api/auth/session/": json({ authenticated: true, user: owner, workspaces: [creatorStudio] }),
      "GET /api/workspaces/": json([creatorStudio]),
      "GET /api/projects/?workspace_id=11": json([]),
    });
    renderApp("/app");

    expect(await screen.findByText(/no projects yet/i)).toBeTruthy();
  });

  test("shows project load errors visibly and can retry", async () => {
    installFetch({
      "GET /api/auth/session/": json({ authenticated: true, user: owner, workspaces: [creatorStudio] }),
      "GET /api/workspaces/": json([creatorStudio]),
      "GET /api/projects/?workspace_id=11": [
        json({ code: "server_error", message: "Projects are temporarily unavailable.", errors: {} }, 503),
        json(projects),
      ],
    });
    const user = userEvent.setup();
    renderApp("/app");

    expect((await screen.findByRole("alert")).textContent).toContain("Projects are temporarily unavailable.");
    expect(screen.getByRole("heading", { name: "Creator Studio", level: 1 })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Launch teaser")).toBeTruthy();
  });

  test("shows a session bootstrap failure instead of hiding it", async () => {
    installFetch({
      "GET /api/auth/session/": new TypeError("Failed to fetch"),
    });
    renderApp("/app");

    expect((await screen.findByRole("alert")).textContent).toMatch(/unable to reach the server/i);
  });

  test("shows workspace load errors", async () => {
    installFetch({
      "GET /api/auth/session/": json({ authenticated: true, user: owner, workspaces: [creatorStudio] }),
      "GET /api/workspaces/": new Response("<h1>Bad gateway</h1>", { status: 502, headers: { "Content-Type": "text/html" } }),
      "GET /api/projects/?workspace_id=11": json(projects),
    });
    renderApp("/app");

    expect((await screen.findByRole("alert")).textContent).toMatch(/502/);
  });
});

describe("home", () => {
  test("keeps the root home route with entry links", () => {
    renderApp("/");
    expect(screen.getByRole("heading", { name: /chameleon/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /get started/i }).getAttribute("href")).toBe("/register");
    expect(screen.getByRole("link", { name: /sign in/i }).getAttribute("href")).toBe("/login");
  });
});
