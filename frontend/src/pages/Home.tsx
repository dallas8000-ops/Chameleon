import React from "react";
import { Link } from "react-router-dom";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl">Chameleon</h1>
      <nav aria-label="Account" className="mt-4 flex gap-4">
        <Link to="/register" className="rounded bg-emerald-600 px-4 py-2 text-white">
          Get started
        </Link>
        <Link to="/login" className="px-4 py-2">
          Sign in
        </Link>
      </nav>
    </main>
  );
}
