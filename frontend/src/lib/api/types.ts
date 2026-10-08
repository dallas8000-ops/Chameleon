export type WorkspaceRole = "owner" | "editor" | "viewer" | (string & {});

export type User = {
  id: number;
  email: string;
};

export type WorkspaceMembership = {
  id: number;
  name: string;
  slug: string;
  role: WorkspaceRole;
};

export type SessionPayload =
  | { authenticated: true; user: User; workspaces: WorkspaceMembership[] }
  | { authenticated: false; user: null; workspaces: [] };

export type AuthenticatedSession = Extract<SessionPayload, { authenticated: true }>;

export type LoginResponse = AuthenticatedSession;

export type RegisterResponse = AuthenticatedSession & {
  workspace: WorkspaceMembership;
};

export type RegisterInput = {
  email: string;
  password: string;
  workspace_name: string;
};

export type LoginInput = {
  email: string;
  password: string;
};

export type Project = {
  id: number;
  workspace_id: number;
  title: string;
  format: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ApiFieldErrors = Record<string, unknown>;

export type ApiErrorBody = {
  code: string;
  message: string;
  errors: ApiFieldErrors;
};

export type CsrfTokenResponse = {
  csrfToken: string;
};
