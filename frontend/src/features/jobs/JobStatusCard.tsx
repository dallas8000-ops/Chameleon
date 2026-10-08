import React from "react";

type JobStatusCardProps = {
  status: string;
  message?: string;
};

export function JobStatusCard({ status, message }: JobStatusCardProps) {
  return (
    <section role="status" className="mt-3 rounded border p-3">
      <h3 className="font-medium">Generation status</h3>
      <p>{status}</p>
      {message ? <p className="text-sm text-gray-700">{message}</p> : null}
    </section>
  );
}
