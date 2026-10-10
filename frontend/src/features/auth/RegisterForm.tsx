import React, { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useSessionStore } from "../../lib/auth/session-store";
import { AuthLayout } from "./AuthLayout";

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
      <label className="field-label">
        Email
        <input
          className="input"
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="field-label">
        Password
        <input
          className="input"
          type="password"
          name="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label className="field-label">
        Workspace name
        <input
          className="input"
          name="workspace_name"
          autoComplete="organization"
          required
          value={workspaceName}
          onChange={(e) => setWorkspaceName(e.target.value)}
        />
      </label>
      <button type="submit" disabled={pending} className="btn btn-primary w-full py-2.5">
        {pending ? "Creating workspace…" : "Create workspace"}
      </button>
    </form>
  );
}

export function RegisterPage() {
  return (
    <AuthLayout
      title="Create your account"
      subtitle="Your workspace keeps projects and media private to its members."
      footer={
        <>
          Already have an account? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <RegisterForm />
    </AuthLayout>
  );
}
