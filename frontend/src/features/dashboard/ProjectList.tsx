import React, { useCallback, useEffect, useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Project } from "../../lib/api/types";

type ProjectListProps = {
  workspaceId: number;
};

type LoadState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; projects: Project[] };

export function ProjectList({ workspaceId }: ProjectListProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

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
        if (!controller.signal.aborted) {
          setState({ status: "error", error });
        }
      },
    );
    return () => controller.abort();
  }, [workspaceId, attempt]);

  return (
    <section aria-labelledby="projects-heading" className="mt-6">
      <h2 id="projects-heading" className="text-xl font-semibold">
        Projects
      </h2>
      {state.status === "loading" && (
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
              <p className="font-medium">{project.title}</p>
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
