import { CoinCounter } from "./CoinCounter";
import type { Player } from "../types/game";

export function Scoreboard({ players }: { players: Player[] }) {
  return (
    <aside className="scoreboard">
      {players.map((player) => (
        <div key={player.id} className={player.status === "spectating" ? "score-row score-row--out" : "score-row"}>
          <span>{player.name}</span>
          <CoinCounter coins={player.coins} />
          <strong>{player.cards.length}</strong>
        </div>
      ))}
    </aside>
  );
}
