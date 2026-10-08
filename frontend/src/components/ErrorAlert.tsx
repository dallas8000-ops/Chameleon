import React from "react";

import { errorMessages } from "../lib/api/client";

type ErrorAlertProps = {
  error: unknown;
  onRetry?: () => void;
};

export function ErrorAlert({ error, onRetry }: ErrorAlertProps) {
  const { message, details } = errorMessages(error);
  return (
    <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
      <p className="font-medium">{message}</p>
      {details.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 rounded border border-red-400 px-2 py-1">
          Retry
        </button>
      )}
    </div>
  );
}
