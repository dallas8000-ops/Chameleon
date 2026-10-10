import React, { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { ErrorAlert } from "../../components/ErrorAlert";
import type { ProjectDetail } from "../../lib/api/types";
import { useAssets } from "./use-assets";
import { useCharacters } from "./use-characters";
import { AiDisclosureToggle } from "./AiDisclosureToggle";
import { AssetPanel } from "./AssetPanel";
import { CaptionCreator } from "./CaptionCreator";
import { CaptionEditor } from "./CaptionEditor";
import { GenerationRoadmap } from "./GenerationRoadmap";
import { SceneDetails } from "./SceneDetails";
import { SceneList } from "./SceneList";
import { ScenePreview } from "./ScenePreview";
import { useProjectDetail } from "./use-project-detail";

export function StudioPage() {
  const { id } = useParams();
  const { sessionStatus, state, canWrite, update, retry } = useProjectDetail(id);

  if (sessionStatus === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  if (state.status === "error") {
    return (
      <AppShell projectId={id}>
        <ErrorAlert error={state.error} onRetry={retry} />
      </AppShell>
    );
  }
  if (state.status === "loading") {
    return (
      <AppShell projectId={id}>
        <p role="status" className="text-muted">Loading studio…</p>
      </AppShell>
    );
  }

  const { project } = state;
  return (
    <AppShell wide projectId={project.id}>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-title">Studio: {project.title}</h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted">
            <span>Format {project.format}</span>
          </p>
          {!canWrite && <p className="mt-1 text-sm text-warn">You have read-only access to this project.</p>}
          <AiDisclosureToggle
            projectId={project.id}
            checked={project.ai_disclosure === true}
            canWrite={canWrite}
            onChanged={(value) => update(() => ({ ai_disclosure: value }))}
          />
        </div>
        <nav aria-label="Project" className="flex items-center gap-2">
          <Link to="/app" className="btn btn-ghost">
            Back to dashboard
          </Link>
          <Link to={`/app/projects/${project.id}/export`} className="btn btn-primary">
            Go to export
          </Link>
        </nav>
      </header>
      <StudioBody project={project} canWrite={canWrite} update={update} />
    </AppShell>
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
  const characters = useCharacters(project.workspace_id);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedIndex = project.scenes.findIndex((scene) => scene.id === selectedId);
  const index = selectedIndex >= 0 ? selectedIndex : project.scenes.length - 1;
  const selected = index >= 0 ? project.scenes[index] : null;

  return (
    <div className="grid gap-6 xl:grid-cols-[18rem_minmax(0,1fr)_22rem]">
      <div className="space-y-6">
        <AssetPanel workspaceId={project.workspace_id} assets={assets.assets} canWrite={canWrite} onUploaded={assets.add} />
        {assets.error ? <ErrorAlert error={assets.error} onRetry={assets.retry} /> : null}
        {characters.error ? <ErrorAlert error={characters.error} onRetry={characters.retry} /> : null}
      </div>
      <div className="space-y-6">
        <ScenePreview format={project.format} scene={selected} sceneNumber={index + 1} assets={assets.assets} />
        <SceneList
          projectId={project.id}
          scenes={project.scenes}
          assets={assets.assets}
          characters={characters.characters}
          canWrite={canWrite}
          selectedId={selected?.id ?? null}
          onSelect={setSelectedId}
          onAdded={(scene) => {
            update((current) => ({ scenes: [...current.scenes, scene] }));
            setSelectedId(scene.id);
          }}
        />
        {selected ? (
          <SceneDetails
            key={selected.id}
            scene={selected}
            index={index}
            total={project.scenes.length}
            characters={characters.characters}
            assets={assets.assets}
            canWrite={canWrite}
            onUpdated={(scene) => update((current) => ({ scenes: current.scenes.map((s) => (s.id === scene.id ? scene : s)) }))}
            onMoved={(sceneId, newIndex) => {
              setSelectedId(sceneId);
              update((current) => {
                const moving = current.scenes.find((s) => s.id === sceneId);
                if (!moving) {
                  return {};
                }
                const reordered = current.scenes.filter((s) => s.id !== sceneId);
                reordered.splice(newIndex, 0, moving);
                return { scenes: reordered.map((s, order) => ({ ...s, order_index: order })) };
              });
            }}
            onDeleted={(sceneId) => {
              update((current) => ({ scenes: current.scenes.filter((s) => s.id !== sceneId).map((s, order) => ({ ...s, order_index: order })) }));
              setSelectedId(null);
            }}
          />
        ) : null}
      </div>
      <div className="space-y-6">
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
        <GenerationRoadmap />
      </div>
    </div>
  );
}
