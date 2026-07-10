import { useState } from "react";
import { Card } from "./Card";
import type { Influence } from "../types/game";

export function CardFan({
  cards,
  hidden = false,
  count,
  selectable = false,
  selected = [],
  onSelect
}: {
  cards: Influence[];
  hidden?: boolean;
  count?: number;
  selectable?: boolean;
  selected?: Influence[];
  onSelect?: (card: Influence) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const items: Array<Influence | undefined> = hidden ? Array.from({ length: count ?? cards.length }) : cards;

  return (
    <div className={expanded ? "card-fan card-fan--expanded" : "card-fan"} onClick={() => setExpanded((value) => !value)}>
      {items.map((card, index) => (
        <Card
          key={`${hidden ? "hidden" : card}-${index}`}
          card={hidden ? undefined : card}
          faceDown={hidden}
          compact={!expanded}
          selected={!hidden && card != null && selected.includes(card)}
          onClick={selectable && card != null ? () => onSelect?.(card) : undefined}
        />
      ))}
    </div>
  );
}
