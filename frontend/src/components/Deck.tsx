import { ASSET_ROOT } from "../data/assets";

export function Deck({ count }: { count: number }) {
  return (
    <div className="deck-stack" aria-label={`${count} cards in deck`}>
      <img src={`${ASSET_ROOT}/raw/deck.png`} alt="" />
      <span>{count}</span>
    </div>
  );
}
