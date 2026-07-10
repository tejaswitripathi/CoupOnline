import type { ActionName, Influence, ResponseName } from "../types/game";
import type {
  AgentActResult,
  GameSummary,
  Observation,
  PrivateView
} from "../types/backend";

const API_ROOT = import.meta.env.VITE_API_ROOT ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init
    });
  } catch (error) {
    throw new ApiError(0, "Could not reach the game server. Is the backend running?", String(error));
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, detail ?? `API request failed: ${response.status}`, detail);
  }

  const payload = await response.json();
  return payload.data as T;
}

export interface SelectCardPayload {
  card?: Influence;
  keep_cards?: Influence[];
}

export const apiClient = {
  createGame(numPlayers: number, playerAgents: Record<number, string>, gameId?: string) {
    return request<GameSummary>("/games", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId, num_players: numPlayers, player_agents: playerAgents })
    });
  },
  privateView(gameId: string, playerId: number, signal?: AbortSignal) {
    return request<PrivateView>(
      `/states/private-view/${playerId}?game_id=${encodeURIComponent(gameId)}`,
      { signal }
    );
  },
  observation(gameId: string, reveal = false, signal?: AbortSignal) {
    return request<Observation>(
      `/states/observation?game_id=${encodeURIComponent(gameId)}&reveal=${reveal ? "true" : "false"}`,
      { signal }
    );
  },
  declareAction(gameId: string, playerId: number, action: ActionName, targetPlayerId?: number) {
    return request("/actions/declare", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId, player_id: playerId, action, target_player_id: targetPlayerId })
    });
  },
  respond(gameId: string, playerId: number, response: ResponseName) {
    return request("/actions/respond", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId, player_id: playerId, response })
    });
  },
  selectCard(gameId: string, playerId: number, payload: SelectCardPayload) {
    return request("/actions/select-card", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId, player_id: playerId, ...payload })
    });
  },
  agentAct(gameId: string, agentName: string, playerId: number, signal?: AbortSignal) {
    return request<AgentActResult>(`/agents/${encodeURIComponent(agentName)}/act`, {
      method: "POST",
      body: JSON.stringify({
        game_id: gameId,
        player_id: playerId,
        data_generation: false,
        include_private_view: false
      }),
      signal
    });
  }
};
