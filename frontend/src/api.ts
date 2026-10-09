import type { Conversation, Health, SendMessageResponse } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0, "network");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.error?.message ?? "Something went wrong. Please try again.",
      response.status,
      body?.error?.code ?? "unknown",
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  createConversation: () => request<Conversation>("/conversations", { method: "POST" }),
  getConversation: (id: string) => request<Conversation>(`/conversations/${id}`),
  sendMessage: (id: string, message: string) =>
    request<SendMessageResponse>(`/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
