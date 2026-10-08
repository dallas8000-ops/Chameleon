import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "../../lib/api/client";
import type { ProjectDetail } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";
import { useLoadErrorHandler } from "../dashboard/use-load-error-handler";

export type ProjectState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; project: ProjectDetail };

/** Loads a project with session recovery; `canWrite` is true only for owner/editor members. */
export function useProjectDetail(id: string | undefined) {
  const sessionStatus = useSessionStore((state) => state.status);
  const workspaces = useSessionStore((state) => state.workspaces);
  const ensureSession = useSessionStore((state) => state.ensureSession);
  const [state, setState] = useState<ProjectState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const showError = useCallback((error: unknown) => setState({ status: "error", error }), []);
  const handleLoadError = useLoadErrorHandler(showError);

  useEffect(() => {
    void ensureSession();
  }, [ensureSession]);

  useEffect(() => {
    if (sessionStatus !== "authenticated") {
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    apiRequest<ProjectDetail>(`/projects/${encodeURIComponent(id ?? "")}/`, { signal: controller.signal }).then(
      (project) => {
        if (!controller.signal.aborted) {
          setState({ status: "ready", project });
        }
      },
      (error: unknown) => {
        void handleLoadError(error, controller.signal);
      },
    );
    return () => controller.abort();
  }, [id, attempt, sessionStatus]);

  const project = state.status === "ready" ? state.project : null;
  const role = project ? workspaces.find((workspace) => workspace.id === project.workspace_id)?.role : undefined;
  const canWrite = role === "owner" || role === "editor";
  const update = useCallback(
    (patch: (current: ProjectDetail) => Partial<ProjectDetail>) =>
      setState((current) => (current.status === "ready" ? { status: "ready", project: { ...current.project, ...patch(current.project) } } : current)),
    [],
  );

  return { sessionStatus, state, canWrite, update, retry: () => setAttempt((value) => value + 1) };
}
