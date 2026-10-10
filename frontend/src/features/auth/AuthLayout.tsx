import React, { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Logo } from "../../components/Logo";

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-8 flex justify-center no-underline hover:no-underline">
          <Logo className="text-lg" />
        </Link>
        <div className="card p-6 sm:p-8">
          <h1 className="text-title">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-muted">{subtitle}</p>
          {children}
        </div>
        <p className="mt-5 text-center text-sm text-muted">{footer}</p>
      </div>
    </main>
  );
}
