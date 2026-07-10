import { ActionCard } from "./ActionCard";
import type { ActionName, Player } from "../types/game";

export function ActionTray({
  actions,
  targets,
  selectedAction,
  onAction,
  onTarget
}: {
  actions: ActionName[];
  targets: Player[];
  selectedAction?: ActionName;
  onAction: (action: ActionName) => void;
  onTarget: (targetId: number) => void;
}) {
  if (actions.length === 0 && !selectedAction) return null;

  return (
    <section className="action-tray">
      <div className="action-tray__timer" />
      <h2>{selectedAction ? `Choose target for ${selectedAction}` : "Choose an action"}</h2>
      {actions.length > 0 ? (
        <div className="action-tray__cards">
          {actions.map((action) => (
            <ActionCard key={action} action={action} selected={action === selectedAction} onClick={() => onAction(action)} />
          ))}
        </div>
      ) : null}
      {selectedAction ? (
        <div className="target-strip">
          {targets.map((target) => (
            <button type="button" key={target.id} onClick={() => onTarget(target.id)}>
              {target.name}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
