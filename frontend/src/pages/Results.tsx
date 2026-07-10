import { Link } from "react-router-dom";
import { PlayerIcon } from "../components/PlayerIcon";
import { VideoBackground } from "../components/VideoBackground";
import { useGame } from "../app/GameContext";

export function Results() {
  const { state, leaveGame } = useGame();
  const winner = state.players.find((player) => player.id === state.winnerId);

  return (
    <main className="screen results-screen">
      <VideoBackground />
      <section className="winner-panel">
        {winner ? <PlayerIcon player={winner} active /> : null}
        <h1>{winner?.name ?? "No one"} wins</h1>
        <Link to="/" onClick={leaveGame}>
          MAIN MENU
        </Link>
      </section>
    </main>
  );
}
