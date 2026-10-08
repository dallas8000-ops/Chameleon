import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "../../lib/api/client";
import type { Asset } from "../../lib/api/types";
import { useLoadErrorHandler } from "../dashboard/use-load-error-handler";

export function useAssets(workspaceId: number) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const showError = useCallback((caught: unknown) => setError(caught), []);
  const handleLoadError = useLoadErrorHandler(showError);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    apiRequest<Asset[]>(`/assets/?workspace_id=${encodeURIComponent(String(workspaceId))}`, { signal: controller.signal }).then(
      (loaded) => {
        if (!controller.signal.aborted) {
          setAssets(loaded);
        }
      },
      (caught: unknown) => {
        void handleLoadError(caught, controller.signal);
      },
    );
    return () => controller.abort();
  }, [workspaceId, attempt]);

  return {
    assets,
    error,
    retry: () => setAttempt((value) => value + 1),
    add: (asset: Asset) => setAssets((current) => [...current, asset]),
  };
}
