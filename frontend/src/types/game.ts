export type Influence = "Duke" | "Assassin" | "Captain" | "Ambassador" | "Contessa";

export type ActionName =
  | "Income"
  | "Foreign Aid"
  | "Tax"
  | "Steal"
  | "Exchange"
  | "Assassinate"
  | "Coup";

export type ResponseName = "pass" | "block" | "challenge";
export type Provider = "human" | "openai" | "claude" | "gemini" | "random" | "empty";
export type Phase =
  | "LOBBY"
  | "AWAITING_ACTION"
  | "AWAITING_TARGET"
  | "AWAITING_RESPONSE"
  | "AWAITING_CARD_SELECTION"
  | "WAITING"
  | "GAME_OVER";

export type PlayerStatus = "active" | "spectating";

export interface Thought {
  public: string;
  private?: string;
}

export interface Player {
  id: number;
  name: string;
  kind: "human" | "agent";
  provider: Provider;
  seatIndex: number;
  cards: Influence[];
  cardCount: number;
  coins: number;
  status: PlayerStatus;
  icon?: string;
  thought?: Thought;
}

export interface LobbySlot {
  id: number;
  name: string;
  provider: Provider;
  icon?: string;
}

export interface PendingResponse {
  action: ActionName;
  actorId: number;
  targetId?: number;
  responders: number[];
  currentResponderIndex: number;
  lastResponse?: {
    responderId: number;
    responderIndex: number;
    response: ResponseName;
  };
}

export interface PendingSelection {
  playerId: number;
  reason: string;
  count: number;
}

export interface GameLogState {
  title: string;
  chosenAction?: ActionName;
  chosenTarget?: string;
  blocks: string[][];
  blockIndex: number;
}

export interface HumanSelection {
  kind: "lose_influence" | "exchange";
  cards?: Influence[];
  candidates?: Influence[];
  keepCount?: number;
}

export interface GameState {
  phase: Phase;
  turnId: number;
  activePlayerId: number;
  humanPlayerId: number;
  players: Player[];
  deckCount: number;
  discardPile: Influence[];
  selectedAction?: ActionName;
  availableActions: ActionName[];
  actionTargetIds: number[];
  pendingAction?: ActionName;
  pendingTargetId?: number;
  responseOptions: ResponseName[];
  selection?: HumanSelection;
  phaseQueue: string[];
  gameLog: GameLogState;
  spectatorMode: boolean;
  winnerId?: number;
  errorMessage?: string;
}

export interface ActionMeta {
  name: ActionName;
  card: string;
  effect: string;
  cost: number;
  target: boolean;
  claim?: Influence;
  blockable: boolean;
  response?: boolean;
}
