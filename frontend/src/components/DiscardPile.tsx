import { useState } from "react";
import { influenceImages } from "../data/assets";
import type { Influence } from "../types/game";
import { Card } from "./Card";

export function DiscardPile({ cards }: { cards: Influence[] }) {
  const [open, setOpen] = useState(false);
  const topCard = cards[cards.length - 1];

  if (!topCard) return null;

  return (
    <>
      <button type="button" className="discard-pile" onClick={() => setOpen(true)}>
        <img src={influenceImages[topCard]} alt="" />
        <span>{cards.length}</span>
      </button>
      {open ? (
        <div className="overlay-panel overlay-panel--top">
          <button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label="Close">
            x
          </button>
          <div className="discard-grid">
            {cards.length > 0 ? cards.map((card, index) => <Card key={`${card}-${index}`} card={card} compact />) : <p>Empty</p>}
          </div>
        </div>
      ) : null}
    </>
  );
}
