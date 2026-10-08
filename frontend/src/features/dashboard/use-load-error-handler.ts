import { useCallback } from "react";

import { ApiError } from "../../lib/api/client";
import { useSessionStore } from "../../lib/auth/session-store";

/**
 * Returns a handler for failed dashboard loads. On 401/403 it re-checks the session first: if the
 * session has expired the store becomes anonymous and the dashboard redirects to sign in.
 */
export function useLoadErrorHandler(onError: (error: unknown) => void) {
  const verifySession = useSessionStore((state) => state.verifySession);
  return useCallback(
    async (error: unknown, signal?: AbortSignal) => {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403) && error.code !== "csrf_failed") {
        try {
          if (!(await verifySession()) || signal?.aborted) {
            return;
          }
        } catch {
          // Fall through and show the original error; the retry button re-runs this check.
        }
      }
      if (!signal?.aborted) {
        onError(error);
      }
    },
    [verifySession, onError],
  );
}
