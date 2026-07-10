import { motion } from "framer-motion";
import { actions } from "../data/assets";
import type { ActionName } from "../types/game";

export function ActionCard({
  action,
  selected = false,
  onClick
}: {
  action: ActionName;
  selected?: boolean;
  onClick?: () => void;
}) {
  const meta = actions[action];

  return (
    <motion.button
      type="button"
      className={selected ? "action-card action-card--selected" : "action-card"}
      onClick={onClick}
      whileHover={{ y: -8, scale: 1.04 }}
      whileTap={{ scale: 0.98 }}
      aria-label={meta.name}
    >
      <img src={meta.card} alt="" />
    </motion.button>
  );
}
