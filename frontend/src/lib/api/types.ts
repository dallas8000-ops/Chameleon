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
  submission_not_accepted?: boolean;
};

export type CsrfTokenResponse = {
  csrfToken: string;
};

export type SceneKind = "script" | "image" | "video" | "presenter";

export type Scene = {
  id: number;
  project_id: number;
  order_index: number;
  kind: SceneKind;
  title: string;
  script_text: string;
  config: Record<string, unknown>;
  character_id?: number | null;
};

export type Character = {
  id: number;
  workspace_id: number;
  name: string;
  role: string;
  description: string;
  face_prompt: string;
  negative_prompt: string;
  voice_notes: string;
  reference_asset_id: number | null;
  created_at: string;
  updated_at: string;
};

export type CharacterInput = Partial<
  Pick<Character, "name" | "role" | "description" | "face_prompt" | "negative_prompt" | "voice_notes" | "reference_asset_id">
>;

export type CaptionSegment = { start: number; end: number; text: string };

export type CaptionTrack = {
  id: number;
  project_id: number;
  language: string;
  segments: CaptionSegment[];
  style: Record<string, unknown>;
  updated_at: string;
};

export type ProjectDetail = Project & { scenes: Scene[]; captions: CaptionTrack[] };

export type ExportRecord = {
  id: number;
  project_id: number;
  status: string;
  format: string;
  settings: Record<string, unknown>;
  error_code: string;
  error_message: string;
  video_available: boolean;
  subtitles_available: boolean;
  created_at: string;
  updated_at: string;
};

export type Asset = {
  id: number;
  workspace_id: number;
  asset_type: "image" | "video" | (string & {});
  source?: "upload" | "generation" | "unknown";
  name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type ProjectFormat = "9:16" | "16:9";
