import type { ChatResponse, MeResponse } from "./types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.toString() ?? "http://localhost:8000";

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function fetchMe() {
  return apiRequest<MeResponse>("/api/me");
}

export function sendChatMessage(message: string) {
  return apiRequest<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message })
  });
}

export function logout() {
  return apiRequest<{ success: boolean }>("/auth/logout", { method: "POST" });
}

