import type { Asset } from "../../lib/api/types";

export function assetSourceLabel(asset: Asset): string {
  if (asset.source === "upload") return "Uploaded";
  if (asset.source === "generation") return "Generated";
  return "Source unknown";
}
