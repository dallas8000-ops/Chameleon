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
    <section aria-labelledby="projects-heading" className="mt-6">
      <h2 id="projects-heading" className="text-xl font-semibold">
        Projects
      </h2>
      {canCreate && (
        <form onSubmit={(event) => void createProject(event)} className="mt-2">
          <label className="block">
            Project title
            <input required maxLength={180} className="block border p-1" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="block">
            Format
            <select className="block border p-1" value={format} onChange={(e) => setFormat(e.target.value as ProjectFormat)}>
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
          <button type="submit" disabled={creating || title.trim() === ""}>
            Create project
          </button>
          {createError ? <ErrorAlert error={createError} /> : null}
        </form>
      )}      {state.status === "loading" && (
        <p role="status" className="mt-2 text-gray-600">
          Loading projects…
        </p>
      )}
      {state.status === "error" && (
        <div className="mt-2">
          <ErrorAlert error={state.error} onRetry={retry} />
        </div>
      )}
      {state.status === "ready" && state.projects.length === 0 && (
        <p className="mt-2 text-gray-600">No projects yet.</p>
      )}
      {state.status === "ready" && state.projects.length > 0 && (
        <ul aria-labelledby="projects-heading" className="mt-2 divide-y divide-gray-200">
          {state.projects.map((project) => (
            <li key={project.id} className="py-2">
              <Link className="font-medium underline" to={`/app/projects/${project.id}/studio`}>
                {project.title}
              </Link>
              <p className="text-sm text-gray-600">
                {project.format} · {project.status}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

