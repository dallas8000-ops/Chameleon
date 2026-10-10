import React from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useSessionStore } from "../lib/auth/session-store";
import { Logo } from "./Logo";

type AppShellProps = {
  children: React.ReactNode;
  /** Wide pages (the studio) use the full width; others are centred. */
  wide?: boolean;
  projectId?: string | number;
};

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium no-underline transition-colors hover:no-underline ${
    isActive ? "bg-raised text-ink" : "text-muted hover:bg-raised/60 hover:text-ink"
  }`;

export function AppShell({ children, wide = false, projectId }: AppShellProps) {
  const navigate = useNavigate();
  const user = useSessionStore((state) => state.user);
  const workspaceName = useSessionStore((state) => state.workspaceName);
  const logout = useSessionStore((state) => state.logout);

  async function signOut() {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_1fr]">
      <aside className="hidden border-r border-line bg-surface/70 p-4 backdrop-blur md:flex md:flex-col">
        <Link to="/app" className="mb-6 px-2 no-underline hover:no-underline">
          <Logo />
        </Link>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-1">
          <NavLink to="/app" end className={navClass}>
            Projects
          </NavLink>
          <NavLink to="/app/characters" className={navClass}>
            Characters
          </NavLink>
          <NavLink to="/app/import" className={navClass}>
            Import script
          </NavLink>
          {projectId !== undefined && (
            <>
              <NavLink to={`/app/projects/${projectId}/studio`} className={navClass}>
                Studio
              </NavLink>
              <NavLink to={`/app/projects/${projectId}/export`} className={navClass}>
                Export
              </NavLink>
            </>
          )}
        </nav>
        <p className="px-2 text-xs leading-relaxed text-faint">
          Image, voice and video generation is on the roadmap and not available yet.
        </p>
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-line bg-surface/60 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3 md:hidden">
            <Link to="/app" className="no-underline hover:no-underline">
              <Logo />
            </Link>
          </div>
          <p className="hidden truncate text-sm text-muted md:block">
            {workspaceName ? <span className="font-medium text-ink">{workspaceName}</span> : "Workspace"}
          </p>
          <div className="flex items-center gap-3">
            {user ? <span className="hidden max-w-[14rem] truncate text-sm text-muted sm:inline">{user.email}</span> : null}
            <button type="button" className="btn btn-ghost" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
        </header>
        <nav aria-label="Main (narrow screens)" className="flex gap-1 overflow-x-auto border-b border-line bg-surface/40 px-4 py-2 md:hidden sm:px-6">
          <NavLink to="/app" end className={navClass}>
            Projects
          </NavLink>
          <NavLink to="/app/characters" className={navClass}>
            Characters
          </NavLink>
                  <NavLink to="/app/import" className={navClass}>
                    Import script
                  </NavLink>
          {projectId !== undefined && (
            <>
              <NavLink to={`/app/projects/${projectId}/studio`} className={navClass}>
                Studio
              </NavLink>
              <NavLink to={`/app/projects/${projectId}/export`} className={navClass}>
                Export
              </NavLink>
            </>
          )}
        </nav>
        <main className={`mx-auto w-full flex-1 px-4 py-6 sm:px-6 sm:py-8 ${wide ? "max-w-[96rem]" : "max-w-5xl"}`}>{children}</main>
      </div>
    </div>
  );
}
