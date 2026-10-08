import { vi } from "vitest";

export type FetchCall = { url: string; method: string; headers: Headers; body: BodyInit | null | undefined; credentials: RequestCredentials | undefined };
type Responder = Response | Error | (() => Response | Promise<Response> | Promise<never>);

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * Routes fetch by "METHOD /path?query". Each route value is a queue of responders consumed in
 * order; the last responder is reused. Unmatched requests fail the test loudly.
 */
export function installFetch(routes: Record<string, Responder | Responder[]>) {
  const calls: FetchCall[] = [];
  const queues = new Map(Object.entries(routes).map(([key, value]) => [key, Array.isArray(value) ? [...value] : [value]]));
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url, method, headers: new Headers(init?.headers), body: init?.body, credentials: init?.credentials });
    const queue = queues.get(`${method} ${url}`);
    if (!queue || queue.length === 0) {
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    }
    const responder = queue.length > 1 ? queue.shift()! : queue[0];
    if (responder instanceof Error) {
      throw responder;
    }
    if (responder instanceof Response) {
      return responder.clone();
    }
    return responder();
  });
  return { calls, spy };
}
