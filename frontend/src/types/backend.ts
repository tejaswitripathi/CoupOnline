import type { ActionName, Influence, ResponseName } from "./game";

export type BackendPhase =
  | "AWAITING_ACTION"
  | "AWAITING_CHALLENGE"
  | "AWAITING_BLOCK_OR_CHALLENGE"
  | "AWAITING_BLOCK_CHALLENGE"
  | "AWAITING_CARD_SELECTION"
  | "RESOLVING"
  | "GAME_OVER";

export interface GameSummary {
  game_id: string;
  turn_id: number;
  phase: BackendPhase;
  acting_player_id: number | null;
  live_player_ids: number[];
  winner_id: number | null;
  num_states: number;
  player_agents: Record<string, string>;
}

export interface PublicPlayerView {
  id: number;
  num_coins: number;
  num_cards: number;
  is_active: boolean;
  cards?: Influence[];
}

export interface LegalDeclaration {
  action: ActionName;
  requires_target: boolean;
  valid_target_ids: number[];
}

export interface LoseInfluenceSelection {
  kind: "lose_influence";
  cards: Influence[];
}

export interface ExchangeSelection {
  kind: "exchange";
  candidates: Influence[];
  keep_count: number;
}

export type LegalSelection = LoseInfluenceSelection | ExchangeSelection | null;

export interface LegalNext {
  declarations: LegalDeclaration[];
  responses: ResponseName[];
  selection: LegalSelection;
}

export interface PendingSelectionRef {
  kind: string;
  player_id: number;
}

export interface Snapshot {
  turn_id: number;
  phase: BackendPhase;
  acting_player_id: number | null;
  victim_id: number | null;
  pending_action: ActionName | null;
  blocked: number;
  challenged: number;
  challenger_id: number | null;
  blocker_id: number | null;
  pending_response_player_ids: number[];
  pending_selection: PendingSelectionRef | null;
  discard_pile: Influence[];
  deck_count: number;
  players: PublicPlayerView[];
  private: {
    player_id: number;
    cards: Influence[];
  };
}

export interface PrivateView {
  player_id: number;
  latest_turn_id: number;
  latest_phase: BackendPhase;
  live_player_ids: number[];
  history: Snapshot[];
  legal_next: LegalNext;
}

export interface Observation {
  game_id: string;
  turn_id: number;
  phase: BackendPhase;
  acting_player_id: number | null;
  victim_id: number | null;
  pending_action: ActionName | null;
  challenger_id: number | null;
  blocker_id: number | null;
  pending_response_player_ids: number[];
  pending_selection: PendingSelectionRef | null;
  discard_pile: Influence[];
  deck_count: number;
  live_player_ids: number[];
  winner_id: number | null;
  players: PublicPlayerView[];
}

export interface AgentDecision {
  command: "declare" | "respond" | "select_card" | "noop";
  action?: ActionName;
  target_player_id?: number;
  response?: ResponseName;
  card?: Influence;
  keep_cards?: Influence[];
}

export interface AgentResult {
  provider: string;
  model: string;
  decision: AgentDecision;
  thoughts?: string | null;
  private_thoughts?: string | null;
  public_thoughts?: string | null;
  raw_output?: unknown;
  fallback?: boolean;
}

export interface AgentActResult {
  agent: AgentResult;
  game: GameSummary;
}
