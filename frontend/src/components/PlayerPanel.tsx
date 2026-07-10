import { CardFan } from "./CardFan";
import { CoinCounter } from "./CoinCounter";
import { PlayerIcon } from "./PlayerIcon";
import { ThoughtBubble } from "./ThoughtBubble";
import type { Player } from "../types/game";

export function PlayerPanel({
  player,
  active = false,
  privateView = false,
  spectatorMode = false
}: {
  player: Player;
  active?: boolean;
  privateView?: boolean;
  spectatorMode?: boolean;
}) {
  return (
    <section className={active ? "player-panel player-panel--active" : "player-panel"}>
      <PlayerIcon player={player} active={active} />
      <div className="player-panel__meta">
        <CoinCounter coins={player.coins} />
      </div>
      <CardFan cards={player.cards} count={player.cardCount} hidden={!privateView && !spectatorMode} />
      <ThoughtBubble thought={player.thought} spectatorMode={spectatorMode} />
    </section>
  );
}
