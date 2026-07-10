import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { PlayerIcon } from "../components/PlayerIcon";
import { VideoBackground } from "../components/VideoBackground";
import { providerIcons } from "../data/assets";
import { useGame } from "../app/GameContext";

export function Lobby() {
  const { lobbySlots, clientSpectator, setClientSpectator, addAgent, removeAgent, beginGame } = useGame();
  const navigate = useNavigate();
  const agentCount = lobbySlots.filter((slot) => slot.provider !== "empty" && slot.provider !== "human").length;
  const canBegin = clientSpectator ? agentCount >= 2 : agentCount >= 1;

  return (
    <main className="screen lobby-screen">
      <VideoBackground />
      <header className="screen-top screen-top--lobby">
        <Link to="/" className="text-link">
          BACK
        </Link>
        <div className="lobby-start-controls">
          <label className="lobby-spectator-toggle">
            <input
              type="checkbox"
              checked={clientSpectator}
              onChange={(event) => setClientSpectator(event.currentTarget.checked)}
            />
            SPECTATE
          </label>
          <button
            type="button"
            className="begin-button begin-button--top"
            disabled={!canBegin}
            onClick={() => {
              beginGame();
              navigate("/game");
            }}
          >
            BEGIN
          </button>
        </div>
      </header>
      <section className="lobby-grid">
        {lobbySlots.slice(1).map((slot, index) => (
          <motion.article
            key={slot.id}
            className={slot.provider === "empty" ? "lobby-slot lobby-slot--empty" : "lobby-slot"}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: index === 1 ? -70 : 20 }}
            transition={{ delay: index * 0.08 }}
          >
            {slot.provider === "empty" ? (
              <button type="button" className="add-player" onClick={() => addAgent(slot.id)} aria-label="Add LLM player">
                +
              </button>
            ) : (
              <>
                <PlayerIcon slot={slot} />
                {providerIcons[slot.provider] ? <img className="provider-badge" src={providerIcons[slot.provider]} alt="" /> : null}
                <strong>{slot.name}</strong>
                <button type="button" className="slot-remove" onClick={() => removeAgent(slot.id)}>
                  REMOVE
                </button>
              </>
            )}
          </motion.article>
        ))}
      </section>
    </main>
  );
}
