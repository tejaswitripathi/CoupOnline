import { AnimatePresence, motion } from "framer-motion";
import type { Thought } from "../types/game";

export function ThoughtBubble({ thought, spectatorMode = false }: { thought?: Thought; spectatorMode?: boolean }) {
  return (
    <AnimatePresence>
      {thought ? (
        <motion.div
          className="thought-bubble"
          initial={{ opacity: 0, y: 8, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.96 }}
          transition={{ duration: 0.25 }}
        >
          <span>{thought.public}</span>
          {spectatorMode && thought.private ? (
            <em>... {thought.private}...</em>
          ) : null}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
