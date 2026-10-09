import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "./api";
import ChatPanel from "./components/ChatPanel";
import DocumentPanel from "./components/DocumentPanel";
import StatePanel from "./components/StatePanel";
import type { Conversation, Health } from "./types";

const STORAGE_KEY = "dia.conversationId";

export default function App() {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const start = useCallback(async () => {
    setError(null);
    setWarnings([]);
    try {
      const created = await api.createConversation();
      sessionStorage.setItem(STORAGE_KEY, created.id);
      setConversation(created);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start a conversation.");
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      // Resume from the backend (source of truth); start fresh if it no longer exists.
      api.getConversation(saved).then(setConversation).catch(() => start());
    } else {
      start();
    }
  }, [start]);

  const send = async () => {
    if (!conversation || loading) return;
    const text = input.trim();
    setLoading(true);
    setError(null);
    setWarnings([]);
    try {
      const result = await api.sendMessage(conversation.id, text);
      setConversation(result.conversation);
      setWarnings(result.warnings);
      setInput("");
    } catch (e) {
      // Keep the text so the user can retry; state was not changed by the failed turn.
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      if (e instanceof ApiError && e.code === "conversation_not_found") start();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header>
        <div>
          <h1>Document Intake Assistant</h1>
          <p>Fictional Personal Wishes Document — a demo, not legal advice.</p>
        </div>
        <div className="header-actions">
          {health && (
            <span className={`pill ${health.llm_configured ? "ok" : "bad"}`}>
              LLM: {health.llm_provider}
              {health.llm_configured ? "" : " (not configured)"}
            </span>
          )}
          <button className="secondary" onClick={start} disabled={loading}>
            New conversation
          </button>
        </div>
      </header>

      {health && !health.llm_configured && (
        <p className="notice error banner">
          The selected AI provider has no API key. Set OPENAI_API_KEY, or run with LLM_PROVIDER=mock.
        </p>
      )}

      {conversation ? (
        <main>
          <ChatPanel
            messages={conversation.messages}
            input={input}
            loading={loading}
            error={error}
            warnings={warnings}
            onInput={setInput}
            onSend={send}
          />
          <StatePanel conversation={conversation} />
          <DocumentPanel doc={conversation.document} />
        </main>
      ) : (
        <p className={error ? "notice error banner" : "banner"}>{error ?? "Starting…"}</p>
      )}
    </div>
  );
}
