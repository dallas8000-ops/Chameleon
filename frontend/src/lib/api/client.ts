import type { ApiErrorBody, ApiFieldErrors, CsrfTokenResponse } from "./types";

const API_PREFIX = "/api";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
const NETWORK_ERROR_MESSAGE = "Unable to reach the server. Check your connection and try again.";
const CSRF_FAILURE_MESSAGE = "The security check failed. Refresh the page and try again.";

export class ApiError extends Error implements ApiErrorBody {
  readonly status: number;
  readonly code: string;
  readonly errors: ApiFieldErrors;
  readonly submission_not_accepted: boolean;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.errors = body.errors;
    this.submission_not_accepted = body.submission_not_accepted === true;
  }
}

let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;

export function clearCsrfToken(): void {
  csrfToken = null;
  csrfRequest = null;
}

async function getCsrfToken(): Promise<string> {
  if (csrfToken) {
    return csrfToken;
  }
  if (!csrfRequest) {
    const request = send<CsrfTokenResponse>("/auth/csrf/", { method: "GET" }).then((body) => {
      if (typeof body?.csrfToken !== "string" || body.csrfToken === "") {
        throw new ApiError(0, { code: "csrf_unavailable", message: "The server did not return a CSRF token.", errors: {} });
      }
      return body.csrfToken;
    });
    csrfRequest = request;
    request.then(
      (token) => {
        if (csrfRequest === request) {
          csrfToken = token;
          csrfRequest = null;
        }
      },
      () => {
        if (csrfRequest === request) {
          csrfRequest = null;
        }
      },
    );
  }
  return csrfRequest;
}

/** Django rotates the CSRF token on login/register; call this afterwards. */
export async function refreshCsrfToken(): Promise<string> {
  clearCsrfToken();
  return getCsrfToken();
}

function assertRelativeApiPath(path: string): void {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("://")) {
    throw new Error(`apiRequest path must be relative to ${API_PREFIX} and start with "/": ${path}`);
  }
}

function isFieldErrors(value: unknown): value is ApiFieldErrors {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function toApiError(response: Response): Promise<ApiError> {
  const fallback: ApiErrorBody = {
    code: `http_${response.status}`,
    message: `Request failed with status ${response.status}.`,
    errors: {},
  };
  const text = await response.text().catch(() => "");
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    // Django's csrf_protect failures render an HTML page rather than the JSON error envelope.
    if (response.status === 403 && /CSRF/i.test(text)) {
      return new ApiError(response.status, { code: "csrf_failed", message: CSRF_FAILURE_MESSAGE, errors: {} });
    }
    return new ApiError(response.status, fallback);
  }
  if (isFieldErrors(body)) {
    if (typeof body.message === "string") {
      return new ApiError(response.status, {
        code: typeof body.code === "string" ? body.code : fallback.code,
        message: body.message,
        errors: isFieldErrors(body.errors) ? body.errors : {},
        submission_not_accepted: body.submission_not_accepted === true,
      });
    }
    if (typeof body.detail === "string") {
      if (response.status === 403 && body.detail.startsWith("CSRF Failed")) {
        return new ApiError(response.status, { code: "csrf_failed", message: CSRF_FAILURE_MESSAGE, errors: {} });
      }
      return new ApiError(response.status, { ...fallback, message: body.detail });
    }
  }
  return new ApiError(response.status, fallback);
}

async function send<T>(path: string, init: RequestInit, retryOnCsrfFailure = true): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  const unsafe = !SAFE_METHODS.has(method);

  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  let usedToken: string | null = null;
  if (unsafe) {
    usedToken = await getCsrfToken();
    headers.set("X-CSRFToken", usedToken);
  }

  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      method,
      headers,
      credentials: "same-origin",
    });
  } catch (error) {
    if (init.signal?.aborted) {
      throw error;
    }
    throw new ApiError(0, { code: "network_error", message: NETWORK_ERROR_MESSAGE, errors: {} });
  }

  if (!response.ok) {
    const error = await toApiError(response);
    if (unsafe && retryOnCsrfFailure && error.code === "csrf_failed") {
      if (csrfToken === usedToken) {
        clearCsrfToken();
      }
      return send<T>(path, init, false);
    }
    throw error;
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }
  const text = await response.text();
  if (text === "") {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(response.status, {
      code: "invalid_response",
      message: "The server returned an unreadable response.",
      errors: {},
    });
  }
}

/**
 * Same-origin request to the Django API. `path` is relative to `/api` (e.g. "/workspaces/").
 * Unsafe methods automatically carry the session's CSRF token.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  assertRelativeApiPath(path);
  return send<T>(path, init);
}

export function errorMessages(error: unknown): { message: string; details: string[] } {
  if (error instanceof ApiError) {
    const details: string[] = [];
    const collect = (value: unknown, label: string | null) => {
      if (typeof value === "string") {
        if (value !== error.message) {
          details.push(label ? `${label}: ${value}` : value);
        }
      } else if (Array.isArray(value)) {
        value.forEach((item) => collect(item, label));
      } else if (isFieldErrors(value)) {
        Object.entries(value).forEach(([key, item]) => collect(item, key === "non_field_errors" ? label : humanize(key)));
      }
    };
    collect(error.errors, null);
    return { message: error.message, details };
  }
  if (error instanceof Error && error.message) {
    return { message: error.message, details: [] };
  }
  return { message: "Something went wrong. Please try again.", details: [] };
}

function humanize(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
