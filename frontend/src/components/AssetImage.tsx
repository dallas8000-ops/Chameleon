import React from "react";

/** Private asset image, served by the authorized content endpoint. */
export function AssetImage({ assetId, className = "" }: { assetId: number; className?: string }) {
  return <img src={`/api/assets/${assetId}/content/`} alt="" loading="lazy" className={`object-cover ${className}`} />;
}
