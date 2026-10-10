import React, { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useSessionStore } from "../../lib/auth/session-store";
import { AuthLayout } from "./AuthLayout";

export function LoginForm() {
  const navigate = useNavigate();
  const login = useSessionStore((state) => state.login);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      await login({ email, password });
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
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <button type="submit" disabled={pending} className="btn btn-primary w-full py-2.5">
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export function LoginPage() {
  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to your workspace."
      footer={
        <>
          New to Chameleon? <Link to="/register">Get started</Link>
        </>
      }
    >
      <LoginForm />
    </AuthLayout>
  );
}
