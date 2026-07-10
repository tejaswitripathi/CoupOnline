import type { GameState, LobbySlot } from "../types/game";

export const defaultLobbySlots: LobbySlot[] = [
  { id: 1, name: "You", provider: "human" },
  { id: 2, name: "", provider: "empty" },
  { id: 3, name: "", provider: "empty" },
  { id: 4, name: "", provider: "empty" }
];

export function emptyGameState(spectatorMode = false): GameState {
  return {
    phase: "LOBBY",
    turnId: 0,
    activePlayerId: 0,
    humanPlayerId: spectatorMode ? 0 : 1,
    players: [],
    deckCount: 0,
    discardPile: [],
    availableActions: [],
    actionTargetIds: [],
    responseOptions: [],
    phaseQueue: [],
    gameLog: {
      title: "",
      blocks: [],
      blockIndex: 0
    },
    spectatorMode
  };
}
