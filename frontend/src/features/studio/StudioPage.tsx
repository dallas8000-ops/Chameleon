import React, { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ProjectDetail } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";
import { useLoadErrorHandler } from "../dashboard/use-load-error-handler";
import { CaptionEditor } from "./CaptionEditor";
import { GenerationPanel } from "./GenerationPanel";
import { SceneList } from "./SceneList";

type State = { status: "loading" } | { status: "error"; error: unknown } | { status: "ready"; project: ProjectDetail };

export function StudioPage() {
  const { id } = useParams();
  const sessionStatus = useSessionStore((state) => state.status);
  const workspaces = useSessionStore((state) => state.workspaces);
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const showError = useCallback((error: unknown) => setState({ status: "error", error }), []);
  const handleLoadError = useLoadErrorHandler(showError);

  useEffect(() => {
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
  }, [id, attempt]);

  if (sessionStatus === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  if (state.status === "loading") {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <p role="status">Loading studio…</p>
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <ErrorAlert error={state.error} onRetry={() => setAttempt((value) => value + 1)} />
      </main>
    );
  }

  const { project } = state;
  const role = workspaces.find((workspace) => workspace.id === project.workspace_id)?.role;
  const canWrite = role !== "viewer";
  const update = (patch: Partial<ProjectDetail>) => setState({ status: "ready", project: { ...project, ...patch } });

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-semibold">Studio: {project.title}</h1>
      <p className="text-sm text-gray-600">Format {project.format}</p>
      <Link to={`/app/projects/${project.id}/export`}>Go to export</Link>
      <SceneList
        projectId={project.id}
        scenes={project.scenes}
        canWrite={canWrite}
        onAdded={(scene) => update({ scenes: [...project.scenes, scene] })}
      />
      <GenerationPanel workspaceId={project.workspace_id} projectId={project.id} canWrite={canWrite} />
      {project.captions.map((caption) => (
        <CaptionEditor
          key={caption.id}
          caption={caption}
          canWrite={canWrite}
          onSaved={(saved) => update({ captions: project.captions.map((c) => (c.id === saved.id ? saved : c)) })}
        />
      ))}
    </main>
  );
}
