import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ActionTray } from "../components/ActionTray";
import { Card } from "../components/Card";
import { CardFan } from "../components/CardFan";
import { Deck } from "../components/Deck";
import { DialogueBox } from "../components/DialogueBox";
import { DiscardPile } from "../components/DiscardPile";
import { Notification } from "../components/Notification";
import { PlayerPanel } from "../components/PlayerPanel";
import { Popup } from "../components/Popup";
import { VideoBackground } from "../components/VideoBackground";
import { useGame } from "../app/GameContext";
import type { Influence } from "../types/game";

export function Game() {
  const {
    state,
    humanPlayer,
    availableActions,
    selectAction,
    selectTarget,
    submitResponse,
    selectInfluence,
    selectExchange,
    leaveGame,
    clearError
  } = useGame();
  const navigate = useNavigate();
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [exchangeKeep, setExchangeKeep] = useState<number[]>([]);

  const isSpectator = state.spectatorMode || !humanPlayer || humanPlayer.status === "spectating";
  const isActing = !isSpectator && (state.phase === "AWAITING_ACTION" || state.phase === "AWAITING_TARGET");
  const screenClass = ["screen", "game-screen", isSpectator && "game-screen--spectator", isActing && "game-screen--acting"]
    .filter(Boolean)
    .join(" ");
  const tablePlayers = state.players.filter((player) => player.kind !== "human");
  const targetPlayers = state.players.filter((player) => state.actionTargetIds.includes(player.id));

  const needsHumanResponse = state.phase === "AWAITING_RESPONSE" && state.responseOptions.length > 0;
  const selectionPrompt = state.phase === "AWAITING_CARD_SELECTION" && !!state.selection;
  const isExchange = selectionPrompt && state.selection?.kind === "exchange";
  const isLoseInfluence = selectionPrompt && state.selection?.kind === "lose_influence";
  const keepCount = state.selection?.keepCount ?? 0;

  const seats = useMemo(
    () => tablePlayers.map((player, index) => ({ player, className: `seat seat-${player.seatIndex || index + 1}` })),
    [tablePlayers]
  );

  useEffect(() => {
    setExchangeKeep([]);
  }, [state.turnId, state.phase]);

  if (state.phase === "LOBBY") return <Navigate to="/play" replace />;
  if (state.phase === "GAME_OVER") return <Navigate to="/results" replace />;

  const toggleExchangeCard = (candidateIndex: number) => {
    setExchangeKeep((current) => {
      const position = current.indexOf(candidateIndex);
      if (position >= 0) {
        const next = [...current];
        next.splice(position, 1);
        return next;
      }
      if (current.length >= keepCount) return current;
      return [...current, candidateIndex];
    });
  };

  const confirmExchange = () => {
    const candidates = state.selection?.candidates ?? [];
    selectExchange(exchangeKeep.map((index) => candidates[index]).filter((card): card is Influence => !!card));
  };

  return (
    <main className={screenClass}>
      <VideoBackground angled />
      <button type="button" className="leave-button" onClick={() => setConfirmLeave(true)}>
        LEAVE
      </button>

      <section className="table-surface">
        <div className="table-center">
          <Deck count={state.deckCount} />
          <DiscardPile cards={state.discardPile} />
        </div>
        {seats.map(({ player, className }) => (
          <div key={player.id} className={className}>
            <PlayerPanel player={player} active={player.id === state.activePlayerId} spectatorMode={state.spectatorMode} />
          </div>
        ))}
      </section>

      {!isSpectator && humanPlayer && humanPlayer.status === "active" ? (
        <section className="private-hand">
          <PlayerPanel
            player={humanPlayer}
            active={humanPlayer.id === state.activePlayerId}
            privateView
            spectatorMode={state.spectatorMode}
          />
          {isLoseInfluence ? <CardFan cards={humanPlayer.cards} selectable onSelect={selectInfluence} /> : null}
        </section>
      ) : null}

      {!isSpectator ? (
        <ActionTray
          actions={state.phase === "AWAITING_ACTION" ? availableActions : []}
          targets={targetPlayers}
          selectedAction={state.phase === "AWAITING_TARGET" ? state.selectedAction : undefined}
          onAction={selectAction}
          onTarget={selectTarget}
        />
      ) : null}

      {needsHumanResponse ? (
        <DialogueBox
          title={`${state.pendingAction ?? "Respond"}?`}
          timerKey={`${state.turnId}-${state.pendingAction}`}
          seconds={10}
        >
          <div className="response-row">
            {state.responseOptions.includes("pass") ? (
              <button type="button" onClick={() => submitResponse("pass")}>
                PASS
              </button>
            ) : null}
            {state.responseOptions.includes("block") ? (
              <button type="button" onClick={() => submitResponse("block")}>
                BLOCK
              </button>
            ) : null}
            {state.responseOptions.includes("challenge") ? (
              <button type="button" onClick={() => submitResponse("challenge")}>
                CHALLENGE
              </button>
            ) : null}
          </div>
        </DialogueBox>
      ) : null}

      {isLoseInfluence ? (
        <DialogueBox title="Lose an influence" timerKey={`${state.turnId}-lose`} seconds={20}>
          <p>Click one of your cards to reveal and discard it.</p>
        </DialogueBox>
      ) : null}

      {isExchange && state.selection?.candidates ? (
        <div className="overlay-panel overlay-panel--top">
          <h2>{`Keep ${keepCount} card${keepCount === 1 ? "" : "s"}`}</h2>
          <div className="discard-grid">
            {state.selection.candidates.map((card, index) => (
              <Card
                key={`${card}-${index}`}
                card={card}
                compact
                selected={exchangeKeep.includes(index)}
                onClick={() => toggleExchangeCard(index)}
              />
            ))}
          </div>
          <button type="button" className="begin-button" disabled={exchangeKeep.length !== keepCount} onClick={confirmExchange}>
            CONFIRM
          </button>
        </div>
      ) : null}

      <Notification log={state.gameLog} />

      {state.errorMessage ? (
        <Popup
          title="Connection problem"
          onConfirm={() => {
            clearError();
            leaveGame();
            navigate("/");
          }}
          onCancel={clearError}
        >
          <p>{state.errorMessage}</p>
        </Popup>
      ) : null}

      {confirmLeave ? (
        <Popup
          title="Leave the game?"
          onConfirm={() => {
            leaveGame();
            navigate("/");
          }}
          onCancel={() => setConfirmLeave(false)}
        >
          <p>The current table will close.</p>
        </Popup>
      ) : null}
    </main>
  );
}
