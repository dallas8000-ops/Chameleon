import React from "react";

import { errorMessages } from "../lib/api/client";

type ErrorAlertProps = {
  error: unknown;
  onRetry?: () => void;
};

export function ErrorAlert({ error, onRetry }: ErrorAlertProps) {
  const { message, details } = errorMessages(error);
  return (
    <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3 text-sm text-danger">
      <p className="font-medium">{message}</p>
      {details.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn btn-danger mt-2 px-2 py-1">
          Retry
        </button>
      )}
    </div>
  );
}
