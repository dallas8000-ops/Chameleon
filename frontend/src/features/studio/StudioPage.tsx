import React from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import type { ProjectDetail } from "../../lib/api/types";
import { useAssets } from "./use-assets";
import { AssetPanel } from "./AssetPanel";
import { CaptionCreator } from "./CaptionCreator";
import { CaptionEditor } from "./CaptionEditor";
import { GenerationPanel } from "./GenerationPanel";
import { SceneList } from "./SceneList";
import { useProjectDetail } from "./use-project-detail";

export function StudioPage() {
  const { id } = useParams();
  const { sessionStatus, state, canWrite, update, retry } = useProjectDetail(id);

  if (sessionStatus === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  if (state.status === "error") {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <ErrorAlert error={state.error} onRetry={retry} />
      </main>
    );
  }
  if (state.status === "loading") {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <p role="status">Loading studio…</p>
      </main>
    );
  }

  const { project } = state;
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-semibold">Studio: {project.title}</h1>
      <p className="text-sm text-gray-600">Format {project.format}</p>
      {!canWrite && <p className="text-sm text-gray-600">You have read-only access to this project.</p>}
      <Link to="/app">Back to dashboard</Link> · <Link to={`/app/projects/${project.id}/export`}>Go to export</Link>
      <StudioBody project={project} canWrite={canWrite} update={update} />
    </main>
  );
}

function StudioBody({
  project,
  canWrite,
  update,
}: {
  project: ProjectDetail;
  canWrite: boolean;
  update: ReturnType<typeof useProjectDetail>["update"];
}) {
  const assets = useAssets(project.workspace_id);
  return (
    <>
      <AssetPanel workspaceId={project.workspace_id} assets={assets.assets} canWrite={canWrite} onUploaded={assets.add} />
      {assets.error ? <ErrorAlert error={assets.error} onRetry={assets.retry} /> : null}
      <SceneList
        projectId={project.id}
        scenes={project.scenes}
        assets={assets.assets}
        canWrite={canWrite}
        onAdded={(scene) => update((current) => ({ scenes: [...current.scenes, scene] }))}
      />
      <GenerationPanel workspaceId={project.workspace_id} projectId={project.id} canWrite={canWrite} onAssetReady={assets.retry} />
      {project.captions.map((caption) => (
        <CaptionEditor
          key={caption.id}
          caption={caption}
          canWrite={canWrite}
          onSaved={(saved) => update((current) => ({ captions: current.captions.map((c) => (c.id === saved.id ? saved : c)) }))}
        />
      ))}
      {canWrite ? (
        <CaptionCreator projectId={project.id} onCreated={(caption) => update((current) => ({ captions: [...current.captions, caption] }))} />
      ) : null}
    </>
  );
}
