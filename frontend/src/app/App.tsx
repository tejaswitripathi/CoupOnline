import { Navigate, Route, Routes } from "react-router-dom";
import { Game } from "../pages/Game";
import { Lobby } from "../pages/Lobby";
import { MainMenu } from "../pages/MainMenu";
import { Results } from "../pages/Results";
import { Rules } from "../pages/Rules";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<MainMenu />} />
      <Route path="/play" element={<Lobby />} />
      <Route path="/game" element={<Game />} />
      <Route path="/rules" element={<Rules />} />
      <Route path="/results" element={<Results />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
