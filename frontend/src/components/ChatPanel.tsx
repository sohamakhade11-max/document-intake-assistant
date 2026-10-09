import { FormEvent, useEffect, useRef } from "react";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  input: string;
  loading: boolean;
  error: string | null;
  warnings: string[];
  onInput: (value: string) => void;
  onSend: () => void;
}

export default function ChatPanel({ messages, input, loading, error, warnings, onInput, onSend }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
  endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
}, [messages, loading]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!loading && input.trim()) onSend();
  };

  return (
    <section className="panel chat" aria-label="Conversation">
      <h2>Conversation</h2>
      <div className="messages" role="log" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            <span className="who">{m.role === "user" ? "You" : "Assistant"}</span>
            {m.content}
          </div>
        ))}
        {loading && <div className="bubble assistant typing">Thinking…</div>}
        <div ref={endRef} />
      </div>
      {warnings.length > 0 && (
        <ul className="notice warn" role="status">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={submit} className="composer">
        <input
          value={input}
          onChange={(e) => onInput(e.target.value)}
          placeholder="Type your answer, or correct something you said earlier…"
          maxLength={2000}
          aria-label="Your message"
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? "Sending…" : "Send"}
        </button>
      </form>
    </section>
  );
}
