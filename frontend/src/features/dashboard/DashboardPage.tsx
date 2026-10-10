import React, { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { WorkspaceMembership } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";
import { ProjectList } from "./ProjectList";
import { useLoadErrorHandler } from "./use-load-error-handler";

export function DashboardPage() {
  const status = useSessionStore((state) => state.status);
  const sessionError = useSessionStore((state) => state.sessionError);
  const ensureSession = useSessionStore((state) => state.ensureSession);
  const reloadSession = useSessionStore((state) => state.reloadSession);

  useEffect(() => {
    void ensureSession();
  }, [ensureSession]);

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppShell>
      {(status === "unknown" || status === "loading") && <p role="status" className="text-muted">Loading your workspace…</p>}
      {status === "error" && <ErrorAlert error={sessionError} onRetry={() => void reloadSession()} />}
      {status === "authenticated" && <WorkspaceDashboard />}
    </AppShell>
  );
}

type WorkspacesState = { status: "loading" } | { status: "error"; error: unknown } | { status: "ready" };

function WorkspaceDashboard() {
  const workspaceName = useSessionStore((state) => state.workspaceName);
  const activeWorkspaceId = useSessionStore((state) => state.activeWorkspaceId);
  const workspaces = useSessionStore((state) => state.workspaces);
  const setWorkspaces = useSessionStore((state) => state.setWorkspaces);
  const [state, setState] = useState<WorkspacesState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const showError = useCallback((error: unknown) => setState({ status: "error", error }), []);
  const handleLoadError = useLoadErrorHandler(showError);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    apiRequest<WorkspaceMembership[]>("/workspaces/", { signal: controller.signal }).then(
      (memberships) => {
        if (!controller.signal.aborted) {
          setWorkspaces(memberships);
          setState({ status: "ready" });
        }
      },
      (error: unknown) => {
        void handleLoadError(error, controller.signal);
      },
    );
    return () => controller.abort();
  }, [setWorkspaces, attempt]);

  const activeRole = workspaces.find((workspace) => workspace.id === activeWorkspaceId)?.role;

  return (
    <>
      <header className="mb-8">
        <p className="text-xs font-medium uppercase tracking-widest text-faint">Workspace</p>
        <h1 className="mt-1 text-title">{workspaceName ?? "Your workspace"}</h1>
        {activeRole && <p className="mt-1 text-sm text-muted">Role: {activeRole}</p>}
      </header>
      {state.status === "loading" && (
        <p role="status" className="text-muted">
          Loading workspaces…
        </p>
      )}
      {state.status === "error" && (
        <div>
          <ErrorAlert error={state.error} onRetry={retry} />
        </div>
      )}
      {state.status === "ready" && activeWorkspaceId === null && (
        <p className="text-muted">You are not a member of any workspace yet.</p>
      )}
      {state.status === "ready" && activeWorkspaceId !== null && <ProjectList workspaceId={activeWorkspaceId} />}
    </>
  );
}
