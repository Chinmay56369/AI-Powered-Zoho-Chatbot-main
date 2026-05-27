import { useEffect, useState } from "react";

import { fetchMe } from "./api";
import { ChatWindow } from "./components/ChatWindow";
import { LoginGate } from "./components/LoginGate";
import type { MeResponse } from "./types";

type Theme = "dark" | "light";

const THEME_STORAGE_KEY = "zoho-project-assistant-theme";

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

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === "dark" || storedTheme === "light") {
    return storedTheme;
  }

  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function App() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

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

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

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
            <div className="sidebar-footer__row">
              <div className="status-badge">
                <span className="status-dot" />
                Assignment Build
              </div>
              <button
                className="theme-switch"
                type="button"
                role="switch"
                aria-checked={theme === "light"}
                aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
                onClick={() => {
                  setTheme((current) => (current === "dark" ? "light" : "dark"));
                }}
              >
                <span
                  className={`theme-switch__icon ${
                    theme === "light" ? "theme-switch__icon--sun" : "theme-switch__icon--moon"
                  }`}
                  aria-hidden="true"
                >
                  {theme === "light" ? (
                    <svg viewBox="0 0 24 24" focusable="false">
                      <circle cx="12" cy="12" r="4.5" />
                      <path d="M12 1.75v3.5M12 18.75v3.5M4.76 4.76l2.48 2.48M16.76 16.76l2.48 2.48M1.75 12h3.5M18.75 12h3.5M4.76 19.24l2.48-2.48M16.76 7.24l2.48-2.48" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" focusable="false">
                      <path d="M14.5 2.4a9 9 0 1 0 7.1 12.9A8.5 8.5 0 0 1 14.5 2.4Z" />
                    </svg>
                  )}
                </span>
                <span className="theme-switch__track" aria-hidden="true">
                  <span className="theme-switch__thumb" />
                </span>
                <span className="sr-only">
                  {theme === "dark" ? "Activate light theme" : "Activate dark theme"}
                </span>
              </button>
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