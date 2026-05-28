import type { PendingAction } from "../types";

type PendingActionCardProps = {
  action: PendingAction;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function PendingActionCard({
  action,
  busy,
  onConfirm,
  onCancel
}: PendingActionCardProps) {
  const previewEntries = Object.entries(action.payload)
    .filter(([, value]) => typeof value === "string" || typeof value === "number")

  return (
    <section className="approval-card">
      <div className="approval-card__content">
        <div className="approval-card__header">
          <p className="section-label">Approval Required</p>
          <span className="route-pill route-pill--warn">{action.action_name}</span>
        </div>
        <h3>{action.summary}</h3>
        {previewEntries.length ? (
          <div className="detail-row">
            {previewEntries.map(([key, value]) => (
              <span key={key} className="detail-pill">
                <strong>{key.replace(/_/g, " ")}</strong>
                {String(value)}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="approval-card__actions">
        <button className="primary-button" disabled={busy} onClick={onConfirm}>
          Confirm
        </button>
        <button className="secondary-button" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}
