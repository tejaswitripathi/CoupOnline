import { useState } from "react";
import { Link } from "react-router-dom";
import { Card } from "../components/Card";
import { VideoBackground } from "../components/VideoBackground";
import { actions, actionOrder, influenceDescriptions } from "../data/assets";
import type { Influence } from "../types/game";

const influenceOrder = Object.keys(influenceDescriptions) as Influence[];

export function Rules() {
  const [tab, setTab] = useState<"influences" | "actions">("influences");

  return (
    <main className="screen rules-screen">
      <VideoBackground />
      <header className="screen-top">
        <Link to="/" className="text-link">
          BACK
        </Link>
      </header>
      <section className="codex-layout">
        <nav className="codex-tabs">
          <button type="button" className={tab === "influences" ? "active" : ""} onClick={() => setTab("influences")}>
            INFLUENCES
          </button>
          <button type="button" className={tab === "actions" ? "active" : ""} onClick={() => setTab("actions")}>
            ACTIONS
          </button>
        </nav>
        <div className="codex-pages">
          {tab === "influences"
            ? influenceOrder.map((influence) => (
                <article key={influence} className="codex-entry">
                  <Card card={influence} compact />
                  <div>
                    <h2>{influence}</h2>
                    <p>{influenceDescriptions[influence]}</p>
                  </div>
                </article>
              ))
            : actionOrder.map((action) => {
                const meta = actions[action];
                return (
                  <article key={action} className="codex-entry">
                    <img className="codex-action-card" src={meta.card} alt="" />
                    <div>
                      <h2>{action}</h2>
                      <p>{meta.effect}</p>
                      <small>{meta.cost > 0 ? `${meta.cost} coins` : meta.blockable ? "Can be blocked" : "Unblockable"}</small>
                    </div>
                  </article>
                );
              })}
        </div>
      </section>
    </main>
  );
}
