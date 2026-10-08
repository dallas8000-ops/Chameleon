import { create } from "zustand";

import { apiRequest, clearCsrfToken, refreshCsrfToken } from "../api/client";
import type {
  LoginInput,
  LoginResponse,
  RegisterInput,
  RegisterResponse,
  SessionPayload,
  User,
  WorkspaceMembership,
} from "../api/types";

export type SessionStatus = "unknown" | "loading" | "authenticated" | "anonymous" | "error";

type SessionData = {
  status: SessionStatus;
  user: User | null;
  workspaces: WorkspaceMembership[];
  activeWorkspaceId: number | null;
  workspaceName: string | null;
  sessionError: unknown;
};

export type SessionState = SessionData & {
  setWorkspaceName: (workspaceName: string | null) => void;
  setWorkspaces: (workspaces: WorkspaceMembership[]) => void;
  ensureSession: () => Promise<void>;
  reloadSession: () => Promise<void>;
  register: (input: RegisterInput) => Promise<RegisterResponse>;
  login: (input: LoginInput) => Promise<LoginResponse>;
};

const initialData: SessionData = {
  status: "unknown",
  user: null,
  workspaces: [],
  activeWorkspaceId: null,
  workspaceName: null,
  sessionError: null,
};

let sessionRequest: Promise<void> | null = null;

function pickWorkspace(workspaces: WorkspaceMembership[], preferredId: number | null): WorkspaceMembership | null {
  return workspaces.find((workspace) => workspace.id === preferredId) ?? workspaces[0] ?? null;
}

function authenticatedData(user: User, workspaces: WorkspaceMembership[], preferredId: number | null): SessionData {
  const active = pickWorkspace(workspaces, preferredId);
  return {
    status: "authenticated",
    user,
    workspaces,
    activeWorkspaceId: active?.id ?? null,
    workspaceName: active?.name ?? null,
    sessionError: null,
  };
}

async function rotateCsrfToken(): Promise<void> {
  try {
    await refreshCsrfToken();
  } catch {
    // The stale token is already discarded, so the next unsafe request fetches a fresh one and
    // surfaces any failure to the user; the login/register itself has already succeeded.
    clearCsrfToken();
  }
}

export const useSessionStore = create<SessionState>((set, get) => ({
  ...initialData,

  setWorkspaceName: (workspaceName) => set({ workspaceName }),

  setWorkspaces: (workspaces) => {
    const active = pickWorkspace(workspaces, get().activeWorkspaceId);
    set({ workspaces, activeWorkspaceId: active?.id ?? null, workspaceName: active?.name ?? null });
  },

  ensureSession: () => {
    const { status } = get();
    if (status === "authenticated" || status === "anonymous") {
      return Promise.resolve();
    }
    return sessionRequest ?? get().reloadSession();
  },

  reloadSession: () => {
    set({ status: "loading", sessionError: null });
    const request = apiRequest<SessionPayload>("/auth/session/").then(
      (session) => {
        if (sessionRequest !== request) {
          return;
        }
        if (session.authenticated) {
          set(authenticatedData(session.user, session.workspaces, get().activeWorkspaceId));
        } else {
          set({ ...initialData, status: "anonymous" });
        }
      },
      (error: unknown) => {
        if (sessionRequest === request) {
          set({ status: "error", sessionError: error });
        }
      },
    );
    sessionRequest = request;
    void request.finally(() => {
      if (sessionRequest === request) {
        sessionRequest = null;
      }
    });
    return request;
  },

  register: async (input) => {
    const result = await apiRequest<RegisterResponse>("/auth/register/", {
      method: "POST",
      body: JSON.stringify(input),
    });
    sessionRequest = null;
    set(authenticatedData(result.user, result.workspaces, result.workspace.id));
    await rotateCsrfToken();
    return result;
  },

  login: async (input) => {
    const result = await apiRequest<LoginResponse>("/auth/login/", {
      method: "POST",
      body: JSON.stringify(input),
    });
    sessionRequest = null;
    set(authenticatedData(result.user, result.workspaces, null));
    await rotateCsrfToken();
    return result;
  },
}));

export function resetSessionStore(): void {
  sessionRequest = null;
  useSessionStore.setState({ ...initialData });
}
