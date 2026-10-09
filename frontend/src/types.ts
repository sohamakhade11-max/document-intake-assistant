// Mirrors backend/app/schemas.py. The backend is the source of truth; the UI only renders it.
export type FieldStatus = "unknown" | "confirmed" | "incomplete" | "needs_clarification";

export interface Gift {
  description: string;
  recipient: string | null;
}

export interface WishesState {
  full_name: string | null;
  home_address: string | null;
  covers_worldwide_assets: boolean | null;
  has_children: boolean | null;
  children: string[];
  executor: { name: string | null; relationship: string | null };
  specific_gifts: Gift[] | null;
  additional_wishes: string[] | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Conflict {
  field: string;
  question: string;
}

export interface DocumentSection {
  heading: string;
  lines: string[];
}

export interface DocumentView {
  title: string;
  disclaimer: string;
  status: "complete" | "draft";
  sections: DocumentSection[];
  text: string;
}

export interface Conversation {
  id: string;
  messages: ChatMessage[];
  state: WishesState;
  field_statuses: Record<string, FieldStatus>;
  missing_required: string[];
  pending_conflicts: Conflict[];
  is_complete: boolean;
  document: DocumentView;
}

export interface SendMessageResponse {
  assistant_message: string;
  warnings: string[];
  conversation: Conversation;
}

export interface Health {
  status: string;
  llm_provider: string;
  llm_configured: boolean;
}
