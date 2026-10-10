import React from "react";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight text-ink ${className}`}>
      <span aria-hidden="true" className="grid h-7 w-7 place-items-center rounded-lg bg-brand-gradient text-sm font-bold text-canvas">
        C
      </span>
      Chameleon
    </span>
  );
}
