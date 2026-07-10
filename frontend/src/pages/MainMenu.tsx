import { Link } from "react-router-dom";
import { ASSET_ROOT } from "../data/assets";
import { VideoBackground } from "../components/VideoBackground";

export function MainMenu() {
  return (
    <main className="screen menu-screen">
      <VideoBackground />
      <section className="menu-stack">
        <img className="brand-logo" src={`${ASSET_ROOT}/raw/logo-transparent.png`} alt="Coup" />
        <nav className="menu-actions">
          <Link to="/play">PLAY</Link>
          <Link to="/rules">RULES</Link>
        </nav>
      </section>
    </main>
  );
}
