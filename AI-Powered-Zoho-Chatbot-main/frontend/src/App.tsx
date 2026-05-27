import { useEffect, useState } from "react";

import { fetchMe } from "./api";
import { ChatWindow } from "./components/ChatWindow";
import { LoginGate } from "./components/LoginGate";
import type { MeResponse } from "./types";

const sidebarItems = [
  {
    label: "Workspace",
    value: "Zoho Projects Copilot"
  },
  {
    label: "Approvals",
    value: "Mutation Guardrail"
  },
  {
    label: "Memory",
    value: "Session Context"
  }
];

export function App() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const response = await fetchMe();
        setMe(response);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Failed to load session state.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <main className="app-shell">
      <div className="shell-noise" />
      <section className="app-layout">
        <aside className="app-sidebar">
          <div className="brand-lockup">
            <div className="brand-lockup__glyph" aria-hidden="true">
              <span />
              <span />
            </div>
            <div>
              <h1>Zoho Project Assistant</h1>
            </div>
          </div>

          <div className="sidebar-section">
            <p className="section-label">Mission</p>
            <h2>Operator Shell</h2>
          </div>

          <div className="sidebar-stack">
            {sidebarItems.map((item) => (
              <article key={item.label} className="sidebar-card">
                <p className="sidebar-card__label">{item.label}</p>
                <h2>{item.value}</h2>
              </article>
            ))}
          </div>

          <footer className="sidebar-footer">
            <div className="status-badge">
              <span className="status-dot" />
              Assignment Build
            </div>
          </footer>
        </aside>

        <section className="main-stage">
          {loading ? (
            <section className="stage-card">
              <p className="section-label">Loading</p>
              <h2>Workspace Restore</h2>
            </section>
          ) : error ? (
            <section className="stage-card">
              <p className="section-label">Connection Error</p>
              <h2>Backend Offline</h2>
              <p>{error}</p>
            </section>
          ) : me?.authenticated && me.user ? (
            <ChatWindow
              me={me.user}
              onLoggedOut={() => {
                setMe({ authenticated: false, login_url: "/auth/login" });
              }}
            />
          ) : (
            <LoginGate />
          )}
        </section>
      </section>
    </main>
  );
}
