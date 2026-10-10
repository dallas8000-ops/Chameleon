import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Project, ProjectFormat } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";
import { useLoadErrorHandler } from "./use-load-error-handler";

type ProjectListProps = {
  workspaceId: number;
};

type LoadState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; projects: Project[] };

export function ProjectList({ workspaceId }: ProjectListProps) {
  const navigate = useNavigate();
  const role = useSessionStore((s) => s.workspaces.find((w) => w.id === workspaceId)?.role);
  const canCreate = role === "owner" || role === "editor";
  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<ProjectFormat>("9:16");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const project = await apiRequest<Project>("/projects/", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, title: title.trim(), format }),
      });
      navigate(`/app/projects/${project.id}/studio`);
    } catch (caught) {
      setCreateError(caught);
      setCreating(false);
    }
  }
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const showError = useCallback((error: unknown) => setState({ status: "error", error }), []);
  const handleLoadError = useLoadErrorHandler(showError);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    apiRequest<Project[]>(`/projects/?workspace_id=${encodeURIComponent(String(workspaceId))}`, {
      signal: controller.signal,
    }).then(
      (projects) => {
        if (!controller.signal.aborted) {
          setState({ status: "ready", projects });
        }
      },
      (error: unknown) => {
        void handleLoadError(error, controller.signal);
      },
    );
    return () => controller.abort();
  }, [workspaceId, attempt]);

  return (
    <section aria-labelledby="projects-heading" className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="order-2 lg:order-1">
        <h2 id="projects-heading" className="mb-4 text-heading">
          Projects
        </h2>
        {state.status === "loading" && (
          <p role="status" className="text-muted">
            Loading projects…
          </p>
        )}
        {state.status === "error" && (
          <div>
            <ErrorAlert error={state.error} onRetry={retry} />
          </div>
        )}
        {state.status === "ready" && state.projects.length === 0 && (
          <p className="card text-center text-muted">No projects yet.</p>
        )}
        {state.status === "ready" && state.projects.length > 0 && (
          <ul aria-labelledby="projects-heading" className="grid gap-4 sm:grid-cols-2">
            {state.projects.map((project) => (
              <li key={project.id} className="card transition hover:border-faint">
                <div
                  aria-hidden="true"
                  className={`mb-4 rounded-lg border border-line bg-canvas ${
                    project.format === "9:16" ? "mx-auto aspect-[9/16] h-28" : "aspect-video w-full"
                  }`}
                />
                <Link className="block truncate font-medium text-ink" to={`/app/projects/${project.id}/studio`}>
                  {project.title}
                </Link>
                <p className="mt-1 flex items-center gap-2 text-xs text-muted">
                  <span className="badge">{project.format}</span>
                  <span>{project.status}</span>
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {canCreate && (
        <form onSubmit={(event) => void createProject(event)} className="card order-1 h-fit space-y-4 lg:order-2">
          <h2 className="text-heading">New project</h2>
          <label className="field-label">
            Project title
            <input required maxLength={180} className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="field-label">
            Format
            <select className="input" value={format} onChange={(e) => setFormat(e.target.value as ProjectFormat)}>
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
          <button type="submit" className="btn btn-primary w-full" disabled={creating || title.trim() === ""}>
            Create project
          </button>
          {createError ? <ErrorAlert error={createError} /> : null}
        </form>
      )}
    </section>
  );
}
