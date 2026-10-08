import React, { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useSessionStore } from "../../lib/auth/session-store";

const inputClass = "mt-1 block w-full rounded border border-gray-300 px-3 py-2";

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
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <button type="submit" disabled={pending} className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-60">
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export function LoginPage() {
  return (
    <main className="mx-auto max-w-md p-6">
      <h1 className="mb-4 text-2xl font-semibold">Sign in</h1>
      <LoginForm />
      <p className="mt-4 text-sm">
        New to Chameleon? <Link to="/register">Get started</Link>
      </p>
    </main>
  );
}
