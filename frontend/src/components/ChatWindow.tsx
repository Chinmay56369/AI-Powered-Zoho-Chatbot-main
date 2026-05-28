import { FormEvent, useState } from "react";

import { logout, sendChatMessage } from "../api";
import type { ChatMessage, MeResponse, PendingAction } from "../types";
import { PendingActionCard } from "./PendingActionCard";

type ChatWindowProps = {
  me: NonNullable<MeResponse["user"]>;
  onLoggedOut: () => void;
};

const starterPrompts = [
  { label: "Projects", prompt: "What projects do I have?" },
  { label: "Tasks", prompt: "Show tasks for the first project" },
  { label: "Workload", prompt: "Who has the most tasks this month?" },
  { label: "Create Task", prompt: "Create a task called API Integration" }
];

function prettifyIdentity(value: string) {
  if (!value.includes("@")) return value;
  return value.split("@")[0].replace(/[._-]+/g, " ");
}

export function ChatWindow({ me, onLoggedOut }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "Ready"
    }
  ]);
  const [input, setInput] = useState("");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const identity = prettifyIdentity(me.display_name);
  const workspace = me.portal_name && me.portal_name !== me.display_name ? me.portal_name : "Zoho Projects";

  async function pushMessage(message: string) {
    setBusy(true);
    setError(null);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message
    };
    setMessages((current) => [...current, userMessage]);

    try {
      const response = await sendChatMessage(message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.reply,
          route: response.route,
          usedTools: response.used_tools ?? []
        }
      ]);
      setPendingAction(response.pending_action ?? null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Something went wrong while sending the message."
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || busy) return;
    setInput("");
    await pushMessage(trimmed);
  }

  async function handleLogout() {
    setBusy(true);
    try {
      await logout();
      onLoggedOut();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="workspace-panel">
      <header className="workspace-header">
        <div>
          <p className="section-label">Zoho Project Assistant</p>
          <h2>{workspace}</h2>
          <p className="workspace-subtitle">{identity}</p>
        </div>
        <div className="workspace-header__actions">
          <span className="status-badge">
            <span className="status-dot status-dot--live" />
            OAuth connected
          </span>
          <button className="secondary-button" onClick={handleLogout} disabled={busy}>
            Logout
          </button>
        </div>
      </header>

      <div className="workspace-body">
        <section className="chat-column">
          <div className="quick-row">
            {starterPrompts.map((prompt) => (
              <button
                key={prompt.label}
                className="quick-chip"
                type="button"
                disabled={busy}
                onClick={() => void pushMessage(prompt.prompt)}
              >
                {prompt.label}
              </button>
            ))}
          </div>

          {pendingAction ? (
            <PendingActionCard
              action={pendingAction}
              busy={busy}
              onConfirm={() => void pushMessage("confirm")}
              onCancel={() => void pushMessage("cancel")}
            />
          ) : null}

          <div className="conversation-panel">
            <div className="message-list">
              {messages.map((message) => (
                <article key={message.id} className={`message-card ${message.role}`}>
                  <div className="message-card__top">
                    <p className="message-role">{message.role === "user" ? "You" : "Assistant"}</p>
                    {message.route ? (
                      <span
                        className={`route-pill ${
                          message.route === "action_agent" ? "route-pill--warn" : ""
                        }`}
                      >
                        {message.route.replace("_", " ")}
                      </span>
                    ) : null}
                  </div>
                  <p className="message-body">{message.content}</p>
                  {message.usedTools?.length ? (
                    <div className="detail-row">
                      {message.usedTools.map((tool) => (
                        <span key={tool} className="detail-pill">
                          {tool}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
              {busy ? <div className="thinking-pill">Thinking…</div> : null}
            </div>

            <form className="composer" onSubmit={handleSubmit}>
              <div className="composer__top">
                <div>
                  <p className="section-label">Command Deck</p>
                </div>
              </div>

              <label className="sr-only" htmlFor="chat-input">
                Chat message
              </label>
              <textarea
                id="chat-input"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Type command"
                rows={4}
                disabled={busy}
              />
              <div className="composer__footer">
                {error ? <p className="error-text">{error}</p> : <span className="composer-note">Ready</span>}
                <button className="primary-button" type="submit" disabled={busy || !input.trim()}>
                  Send
                </button>
              </div>
            </form>
          </div>
        </section>

        <aside className="insight-column">
          <article className="insight-card">
            <p className="section-label">Runtime</p>
            <h3>Multi-agent graph</h3>
          </article>
          <article className="insight-card">
            <p className="section-label">Current Session</p>
            <div className="insight-metric">
              <span>Portal</span>
              <strong>{workspace}</strong>
            </div>
            <div className="insight-metric">
              <span>User</span>
              <strong>{identity}</strong>
            </div>
            <div className="insight-metric">
              <span>Approval mode</span>
              <strong>Enabled</strong>
            </div>
          </article>
          <article className="insight-card insight-card--terminal">
            <p className="section-label">Modes</p>
            <div className="detail-row">
              <span className="detail-pill">Query</span>
              <span className="detail-pill">Action</span>
              <span className="detail-pill">Memory</span>
            </div>
          </article>
        </aside>
      </div>
    </section>
  );
}
