import React, { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Project, ProjectDetail, ProjectFormat } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";
import { useProjectDetail } from "../studio/use-project-detail";
import { CharactersStep } from "./CharactersStep";
import { ScriptStep } from "./ScriptStep";

/** The order automatic mode asks for information in. Each step opens only after the one before it. */
export const AUTO_STEPS = ["Basics", "Script", "Characters", "Build", "Export"] as const;
export type AutoStep = (typeof AUTO_STEPS)[number];

function StepIndicator({ current }: { current: AutoStep }) {
  const currentIndex = AUTO_STEPS.indexOf(current);
  return (
    <ol aria-label="Steps" className="mb-6 flex flex-wrap gap-2">
      {AUTO_STEPS.map((step, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "locked";
        return (
          <li
            key={step}
            aria-current={state === "current" ? "step" : undefined}
            className={`badge ${state === "current" ? "border-brand text-ink" : state === "done" ? "text-muted" : "text-faint"}`}
          >
            {index + 1}. {step}
            {state === "done" ? " (done)" : null}
          </li>
        );
      })}
    </ol>
  );
}

function AutoHeader() {
  return (
    <header className="mb-4">
      <h1 className="text-title">Automatic mode</h1>
      <p className="mt-1 text-sm text-muted">Answer each step in order and the app builds the video for you.</p>
    </header>
  );
}

/** `/app/auto`: step 1, the basics. Creates the project, then moves on to the script step. */
export function AutoStartPage() {
  const status = useSessionStore((state) => state.status);
  const ensureSession = useSessionStore((state) => state.ensureSession);

  useEffect(() => {
    void ensureSession();
  }, [ensureSession]);

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  return (
    <AppShell>
      <AutoHeader />
      <StepIndicator current="Basics" />
      {status === "authenticated" ? <BasicsStep /> : <p role="status" className="text-muted">Loading…</p>}
    </AppShell>
  );
}

function BasicsStep() {
  const navigate = useNavigate();
  const workspaceId = useSessionStore((state) => state.activeWorkspaceId);
  const role = useSessionStore((state) => state.workspaces.find((w) => w.id === state.activeWorkspaceId)?.role);
  const canWrite = role === "owner" || role === "editor";
  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<ProjectFormat>("9:16");
  // No default: the app must ask, because the answer controls the AI label on export.
  const [aiPeople, setAiPeople] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (workspaceId === null) {
    return <p className="text-muted">You are not a member of any workspace yet.</p>;
  }
  if (!canWrite) {
    return <p className="card text-warn">You have read-only access to this workspace, so you cannot start a project.</p>;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const project = await apiRequest<Project>("/projects/", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, title: title.trim(), format, ai_disclosure: aiPeople === true }),
      });
      navigate(`/app/auto/${project.id}`);
    } catch (caught) {
      setError(caught);
      setSaving(false);
    }
  }

  const ready = title.trim() !== "" && aiPeople !== null;
  return (
    <form onSubmit={(event) => void submit(event)} className="card max-w-xl space-y-5" aria-labelledby="basics-heading">
      <h2 id="basics-heading" className="text-heading">
        Step 1: Basics
      </h2>
      <label className="field-label">
        What is the video called?
        <input required maxLength={180} className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="field-label">
        Video shape
        <select className="input" value={format} onChange={(e) => setFormat(e.target.value as ProjectFormat)}>
          <option value="9:16">9:16 (vertical, for phones)</option>
          <option value="16:9">16:9 (widescreen)</option>
        </select>
      </label>
      <fieldset className="space-y-2">
        <legend className="field-label">Will the video show AI-generated people?</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="ai-people" className="h-4 w-4 accent-brand" checked={aiPeople === true} onChange={() => setAiPeople(true)} />
          Yes
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="ai-people" className="h-4 w-4 accent-brand" checked={aiPeople === false} onChange={() => setAiPeople(false)} />
          No
        </label>
      </fieldset>
      <button type="submit" className="btn btn-primary w-full" disabled={saving || !ready}>
        Continue to script
      </button>
      {error ? <ErrorAlert error={error} /> : null}
    </form>
  );
}

/** The first step a saved project still needs, so a project started anywhere resumes in the right place. */
export function nextStep(project: ProjectDetail, charactersConfirmed: boolean): AutoStep {
  if (project.scenes.length === 0) {
    return "Script";
  }
  // The characters step always asks once per visit, so missing images and voice notes are seen before building.
  return charactersConfirmed ? "Build" : "Characters";
}

/** `/app/auto/:id`: resumes any project at its first unfinished step. */
export function AutoProjectPage() {
  const { id } = useParams();
  const { sessionStatus, state, canWrite, retry } = useProjectDetail(id);
  const [charactersConfirmed, setCharactersConfirmed] = useState(false);

  if (sessionStatus === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  const step = state.status === "ready" ? nextStep(state.project, charactersConfirmed) : null;
  return (
    <AppShell projectId={id}>
      <AutoHeader />
      {step ? <StepIndicator current={step} /> : null}
      {state.status === "loading" ? <p role="status" className="text-muted">Loading project…</p> : null}
      {state.status === "error" ? <ErrorAlert error={state.error} onRetry={retry} /> : null}
      {state.status === "ready" ? (
        <div className="max-w-3xl space-y-4">
          <p className="text-sm text-muted">
            {state.project.title} · {state.project.format} · AI-generated people: {state.project.ai_disclosure ? "yes" : "no"}
            {state.project.scenes.length > 0
              ? ` · ${state.project.scenes.length} ${state.project.scenes.length === 1 ? "scene" : "scenes"}`
              : null}
          </p>
          {!canWrite ? (
            <p className="card text-warn">You have read-only access to this project.</p>
          ) : step === "Script" ? (
            <ScriptStep project={state.project} onDone={retry} />
          ) : step === "Characters" ? (
            <CharactersStep project={state.project} onDone={() => setCharactersConfirmed(true)} />
          ) : (
            <NotBuiltYet project={state.project} step={step ?? "Build"} />
          )}
        </div>
      ) : null}
    </AppShell>
  );
}

function NotBuiltYet({ project, step }: { project: ProjectDetail; step: AutoStep }) {
  return (
    <section className="card space-y-3" aria-labelledby="next-step-heading">
      <h2 id="next-step-heading" className="text-heading">
        Step {AUTO_STEPS.indexOf(step) + 1}: {step}
      </h2>
      <p className="text-muted">This step is not built yet. You can carry on in the studio for now.</p>
      <Link to={`/app/projects/${project.id}/studio`} className="btn btn-ghost">
        Open in studio
      </Link>
    </section>
  );
}
