import { motion } from "framer-motion";
import { ASSET_ROOT, influenceImages } from "../data/assets";
import type { Influence } from "../types/game";

export function Card({
  card,
  faceDown = false,
  selected = false,
  compact = false,
  onClick
}: {
  card?: Influence;
  faceDown?: boolean;
  selected?: boolean;
  compact?: boolean;
  onClick?: () => void;
}) {
  const src = faceDown || !card ? `${ASSET_ROOT}/raw/card-face-down.png` : influenceImages[card];

  return (
    <motion.button
      type="button"
      className={[
        "coup-card",
        compact ? "coup-card--compact" : "",
        selected ? "coup-card--selected" : "",
        onClick ? "coup-card--interactive" : ""
      ].join(" ")}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
      whileHover={onClick ? { y: -8, scale: compact ? 1.04 : 1.08 } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      aria-label={card ?? "Hidden card"}
    >
      <motion.img
        src={src}
        alt=""
        initial={false}
        animate={{ rotateY: faceDown ? 180 : 0 }}
        transition={{ duration: 0.35 }}
      />
    </motion.button>
  );
}
