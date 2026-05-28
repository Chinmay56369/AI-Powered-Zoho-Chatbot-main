export type MeResponse = {
  authenticated: boolean;
  login_url?: string | null;
  user?: {
    id: number;
    display_name: string;
    email?: string | null;
    portal_id?: string | null;
    portal_name?: string | null;
  } | null;
};

export type PendingAction = {
  id: string;
  action_name: string;
  summary: string;
  payload: Record<string, unknown>;
};

export type ChatResponse = {
  reply: string;
  route: string;
  pending_action?: PendingAction | null;
  active_project_name?: string | null;
  used_tools?: string[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  route?: string;
  usedTools?: string[];
};

