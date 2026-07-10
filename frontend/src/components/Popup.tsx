import type { ReactNode } from "react";

export function Popup({
  title,
  children,
  onConfirm,
  onCancel
}: {
  title: string;
  children: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="modal-scrim">
      <section className="popup">
        <h2>{title}</h2>
        <div>{children}</div>
        <footer>
          <button type="button" onClick={onConfirm}>
            YES
          </button>
          <button type="button" onClick={onCancel}>
            NO
          </button>
        </footer>
      </section>
    </div>
  );
}
