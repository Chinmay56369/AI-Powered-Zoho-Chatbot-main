import { API_BASE_URL } from "../api";

const loginSteps = [
  "Authenticate",
  "Authorize",
  "Return"
];

export function LoginGate() {
  return (
    <section className="stage-card login-stage">
      <div className="stage-card__header">
        <div>
          <p className="section-label">Zoho OAuth Required</p>
          <h2>Connect Zoho Projects</h2>
        </div>
        <span className="status-badge status-badge--warning">Private Tokens</span>
      </div>

      <div className="login-sequence">
        {loginSteps.map((step, index) => (
          <article key={step} className="login-step">
            <span>{`0${index + 1}`}</span>
            <p>{step}</p>
          </article>
        ))}
      </div>

      <div className="stage-card__footer">
        <a className="primary-button" href={`${API_BASE_URL}/auth/login`}>
          Continue with Zoho
        </a>
      </div>
    </section>
  );
}
