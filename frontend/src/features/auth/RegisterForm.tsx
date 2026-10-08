import React, { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useSessionStore } from "../../lib/auth/session-store";

const inputClass = "mt-1 block w-full rounded border border-gray-300 px-3 py-2";

export function RegisterForm() {
  const navigate = useNavigate();
  const register = useSessionStore((state) => state.register);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      await register({ email, password, workspace_name: workspaceName });
      navigate("/app", { replace: true });
    } catch (caught) {
      setError(caught);
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} aria-busy={pending} className="space-y-4" noValidate>
      {error !== null && <ErrorAlert error={error} />}
      <label className="block">
        Email
        <input
          className={inputClass}
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="block">
        Password
        <input
          className={inputClass}
          type="password"
          name="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label className="block">
        Workspace name
        <input
          className={inputClass}
          name="workspace_name"
          autoComplete="organization"
          required
          value={workspaceName}
          onChange={(e) => setWorkspaceName(e.target.value)}
        />
      </label>
      <button type="submit" disabled={pending} className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-60">
        {pending ? "Creating workspace…" : "Create workspace"}
      </button>
    </form>
  );
}

export function RegisterPage() {
  return (
    <main className="mx-auto max-w-md p-6">
      <h1 className="mb-4 text-2xl font-semibold">Create your account</h1>
      <RegisterForm />
      <p className="mt-4 text-sm">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </main>
  );
}
