import type { CSSProperties } from "react";
import { providerColors } from "../data/assets";
import type { LobbySlot, Player, Provider } from "../types/game";

export function PlayerIcon({ player, slot, active = false }: { player?: Player; slot?: LobbySlot; active?: boolean }) {
  const provider = (player?.provider ?? slot?.provider ?? "human") as Provider;
  const name = player?.name ?? slot?.name ?? "";
  const icon = player?.icon ?? slot?.icon;

  return (
    <div
      className={active ? "player-icon player-icon--active" : "player-icon"}
      style={{ "--player-color": providerColors[provider] } as CSSProperties}
    >
      {icon ? <img src={icon} alt="" /> : <span>{name.slice(0, 1) || "+"}</span>}
    </div>
  );
}
