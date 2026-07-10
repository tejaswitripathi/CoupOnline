import type { GameLogState } from "../types/game";

export function Notification({ log }: { log: GameLogState }) {
  const block = log.blocks[log.blockIndex] ?? [];

  return (
    <aside className="game-log">
      <section className="game-log__left">
        <p className="game-log__turn">{log.title}</p>
        {log.chosenAction ? (
          <div className="game-log__action">
            <span>Chosen action:</span>
            <strong>{log.chosenAction}</strong>
            {log.chosenTarget ? <span className="game-log__target">against {log.chosenTarget}</span> : null}
          </div>
        ) : null}
      </section>
      <section className="game-log__right">
        {block.map((line, index) => (
          <p key={`${line}-${index}`}>{line}</p>
        ))}
      </section>
    </aside>
  );
}
