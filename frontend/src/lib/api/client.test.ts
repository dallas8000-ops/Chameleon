import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { installFetch, json } from "../../test/fetch-mock";
import { ApiError, apiRequest, clearCsrfToken, refreshCsrfToken } from "./client";

beforeEach(() => {
  clearCsrfToken();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("apiRequest", () => {
  test("sends same-origin GETs without CSRF or JSON content type", async () => {
    const { calls } = installFetch({ "GET /api/workspaces/": json([{ id: 1 }]) });

    await expect(apiRequest("/workspaces/")).resolves.toEqual([{ id: 1 }]);
    expect(calls).toHaveLength(1);
    expect(calls[0].credentials).toBe("same-origin");
    expect(calls[0].headers.get("Content-Type")).toBeNull();
    expect(calls[0].headers.get("X-CSRFToken")).toBeNull();
  });

  test("fetches the CSRF token once and reuses it for unsafe requests", async () => {
    const { calls } = installFetch({
      "GET /api/auth/csrf/": json({ csrfToken: "token-1" }),
      "POST /api/things/": json({ ok: true }, 201),
      "DELETE /api/things/1/": new Response(null, { status: 204 }),
    });

    await apiRequest("/things/", { method: "POST", body: JSON.stringify({ a: 1 }) });
    await expect(apiRequest("/things/1/", { method: "DELETE" })).resolves.toBeUndefined();

    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual(["GET /api/auth/csrf/", "POST /api/things/", "DELETE /api/things/1/"]);
    expect(calls[1].headers.get("X-CSRFToken")).toBe("token-1");
    expect(calls[1].headers.get("Content-Type")).toBe("application/json");
    expect(calls[2].headers.get("X-CSRFToken")).toBe("token-1");
    expect(calls[2].headers.get("Content-Type")).toBeNull();
  });

  test("does not set a JSON content type for FormData bodies and keeps caller headers", async () => {
    const { calls } = installFetch({
      "GET /api/auth/csrf/": json({ csrfToken: "token-1" }),
      "POST /api/assets/": json({ id: 3 }, 201),
    });
    const form = new FormData();
    form.append("name", "clip");

    await apiRequest("/assets/", { method: "POST", body: form, headers: { "X-Trace": "abc" } });

    expect(calls[1].headers.get("Content-Type")).toBeNull();
    expect(calls[1].headers.get("X-Trace")).toBe("abc");
    expect(calls[1].headers.get("X-CSRFToken")).toBe("token-1");
    expect(calls[1].body).toBe(form);
  });

  test("uses a refreshed token after rotation", async () => {
    const { calls } = installFetch({
      "GET /api/auth/csrf/": [json({ csrfToken: "token-1" }), json({ csrfToken: "token-2" })],
      "POST /api/things/": json({ ok: true }),
    });

    await apiRequest("/things/", { method: "POST" });
    await refreshCsrfToken();
    await apiRequest("/things/", { method: "POST" });

    expect(calls[1].headers.get("X-CSRFToken")).toBe("token-1");
    expect(calls[3].headers.get("X-CSRFToken")).toBe("token-2");
  });

  test("retries once with a fresh token when Django rejects the CSRF token", async () => {
    const { calls } = installFetch({
      "GET /api/auth/csrf/": [json({ csrfToken: "stale" }), json({ csrfToken: "fresh" })],
      "POST /api/things/": [json({ detail: "CSRF Failed: CSRF token incorrect." }, 403), json({ ok: true })],
    });

    await expect(apiRequest("/things/", { method: "POST", body: "{}" })).resolves.toEqual({ ok: true });
    expect(calls.map((c) => c.headers.get("X-CSRFToken"))).toEqual([null, "stale", null, "fresh"]);
  });

  test("retries once when Django's HTML CSRF failure page rejects an auth POST", async () => {
    const csrfPage = () => new Response("<h1>Forbidden (403)</h1><p>CSRF verification failed. Request aborted.</p>", { status: 403, headers: { "Content-Type": "text/html" } });
    const { calls } = installFetch({
      "GET /api/auth/csrf/": [json({ csrfToken: "stale" }), json({ csrfToken: "fresh" })],
      "POST /api/auth/login/": [csrfPage, json({ authenticated: true })],
    });

    await expect(apiRequest("/auth/login/", { method: "POST", body: "{}" })).resolves.toEqual({ authenticated: true });
    expect(calls.map((c) => c.headers.get("X-CSRFToken"))).toEqual([null, "stale", null, "fresh"]);
  });

  test("surfaces a readable error when the CSRF retry also fails", async () => {
    const csrfPage = () => new Response("<p>CSRF verification failed.</p>", { status: 403, headers: { "Content-Type": "text/html" } });
    const { calls } = installFetch({
      "GET /api/auth/csrf/": [json({ csrfToken: "a" }), json({ csrfToken: "b" })],
      "POST /api/auth/login/": csrfPage,
    });

    await expect(apiRequest("/auth/login/", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 403,
      code: "csrf_failed",
      message: expect.stringMatching(/security check failed/i),
    });
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(2);
  });

  test("throws ApiError with the backend error body", async () => {
    installFetch({
      "GET /api/projects/?workspace_id=x": json(
        { code: "validation_error", message: "Project query is invalid.", errors: { workspace_id: ["A valid integer is required."] } },
        400,
      ),
    });

    const error = await apiRequest("/projects/?workspace_id=x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 400,
      code: "validation_error",
      message: "Project query is invalid.",
      errors: { workspace_id: ["A valid integer is required."] },
    });
  });

  test("normalises DRF detail errors and non-JSON failures", async () => {
    installFetch({
      "GET /api/workspaces/": [
        json({ detail: "Authentication credentials were not provided." }, 403),
        new Response("<h1>Bad gateway</h1>", { status: 502, headers: { "Content-Type": "text/html" } }),
      ],
    });

    await expect(apiRequest("/workspaces/")).rejects.toMatchObject({ status: 403, message: "Authentication credentials were not provided." });
    await expect(apiRequest("/workspaces/")).rejects.toMatchObject({ status: 502, code: "http_502", message: "Request failed with status 502." });
  });

  test("wraps network failures in a readable ApiError", async () => {
    installFetch({ "GET /api/workspaces/": new TypeError("Failed to fetch") });

    await expect(apiRequest("/workspaces/")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: expect.stringMatching(/unable to reach the server/i),
    });
  });

  test("rejects paths that could leave the same-origin API", async () => {
    const { spy } = installFetch({});
    await expect(apiRequest("https://evil.example/api/x")).rejects.toThrow(/relative/);
    await expect(apiRequest("//evil.example/x")).rejects.toThrow(/relative/);
    await expect(apiRequest("workspaces/")).rejects.toThrow(/relative/);
    expect(spy).not.toHaveBeenCalled();
  });
});
