import { AlertIcon } from "../../lib/icons";

export function ApiOfflineBanner({ offline }: { offline: boolean }) {
  if (!offline) return null;
  return (
    <div
      className="row"
      style={{
        background: "var(--rose-bg)",
        color: "var(--rose)",
        borderBottom: "1px solid var(--border)",
        padding: "8px 16px",
        fontSize: 12,
        gap: 8
      }}
    >
      <AlertIcon size={13} />
      <span>API unreachable — start the backend with start.bat or `ad-classifier api`</span>
    </div>
  );
}
