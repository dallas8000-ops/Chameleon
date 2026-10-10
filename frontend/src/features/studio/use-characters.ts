import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "../../lib/api/client";
import type { Character } from "../../lib/api/types";
import { useLoadErrorHandler } from "../dashboard/use-load-error-handler";

export function useCharacters(workspaceId: number | null) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const showError = useCallback((caught: unknown) => setError(caught), []);
  const handleLoadError = useLoadErrorHandler(showError);

  useEffect(() => {
    if (workspaceId === null) {
      return;
    }
    const controller = new AbortController();
    setError(null);
    apiRequest<Character[]>(`/characters/?workspace_id=${encodeURIComponent(String(workspaceId))}`, { signal: controller.signal }).then(
      (loaded) => {
        if (!controller.signal.aborted) {
          setCharacters(loaded);
        }
      },
      (caught: unknown) => {
        void handleLoadError(caught, controller.signal);
      },
    );
    return () => controller.abort();
  }, [workspaceId, attempt]);

  return {
    characters,
    error,
    retry: () => setAttempt((value) => value + 1),
    upsert: (character: Character) =>
      setCharacters((current) =>
        current.some((item) => item.id === character.id)
          ? current.map((item) => (item.id === character.id ? character : item))
          : [...current, character].sort((a, b) => a.name.localeCompare(b.name)),
      ),
    remove: (id: number) => setCharacters((current) => current.filter((item) => item.id !== id)),
  };
}
