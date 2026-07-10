import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { providerIcons } from "../data/assets";
import { defaultLobbySlots, emptyGameState } from "../data/demoGame";
import { ApiError, apiClient } from "../api/client";
import type {
  ActionName,
  GameState,
  HumanSelection,
  Influence,
  LobbySlot,
  Player,
  Provider,
  ResponseName,
  Thought
} from "../types/game";
import type {
  BackendPhase,
  LegalDeclaration,
  LegalNext,
  Observation,
  PendingSelectionRef,
  PrivateView,
  PublicPlayerView,
  AgentResult,
  AgentDecision
} from "../types/backend";

interface GameContextValue {
  lobbySlots: LobbySlot[];
  clientSpectator: boolean;
  state: GameState;
  humanPlayer?: Player;
  availableActions: ActionName[];
  addAgent: (slotId: number) => void;
  removeAgent: (slotId: number) => void;
  setClientSpectator: (value: boolean) => void;
  beginGame: () => void;
  leaveGame: () => void;
  selectAction: (action: ActionName) => void;
  selectTarget: (targetId: number) => void;
  submitResponse: (response: ResponseName) => void;
  selectInfluence: (card: Influence) => void;
  selectExchange: (keepCards: Influence[]) => void;
  clearError: () => void;
}

const GameContext = createContext<GameContextValue | null>(null);

const PACING_MS = 900;
const BLOCK_REVEAL_MS = 1700;

const agentCycle: Array<{ provider: Provider; name: string }> = [
  { provider: "openai", name: "GPT-5" },
  { provider: "claude", name: "Claude" },
  { provider: "gemini", name: "Gemini" },
  { provider: "random", name: "Heuristic" }
];

const providerNames: Record<Provider, string> = {
  human: "You",
  openai: "GPT-5",
  claude: "Claude",
  gemini: "Gemini",
  random: "Heuristic",
  empty: "Empty"
};

const providerToAgentName: Partial<Record<Provider, string>> = {
  openai: "gpt",
  claude: "claude",
  gemini: "gemini",
  random: "random"
};

interface RosterEntry {
  id: number;
  name: string;
  kind: "human" | "agent";
  provider: Provider;
  seatIndex: number;
  icon?: string;
}

interface BoardView {
  phase: BackendPhase;
  turnId: number;
  actingPlayerId: number | null;
  pendingResponders: number[];
  pendingSelection: PendingSelectionRef | null;
  pendingAction: ActionName | null;
  victimId: number | null;
  challengerId: number | null;
  blockerId: number | null;
  discardPile: Influence[];
  deckCount: number;
  winnerId: number | null;
  players: PublicPlayerView[];
  ownPlayerId?: number;
  ownCards?: Influence[];
  legalNext?: LegalNext;
}

interface Narration {
  before: BoardView;
  decision: AgentDecision;
  actorId: number;
}

interface LogState {
  title: string;
  chosenAction?: ActionName;
  chosenTarget?: string;
  blocks: string[][];
}

const delay = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function buildRoster(slots: LobbySlot[], spectator: boolean) {
  const activeSlots = slots.filter(
    (slot) => slot.provider !== "empty" && !(spectator && slot.provider === "human")
  );
  let tableSeat = 1;
  const entries: RosterEntry[] = activeSlots.map((slot, index) => {
    const kind = slot.provider === "human" ? "human" : "agent";
    return {
      id: index + 1,
      name: slot.name || providerNames[slot.provider],
      kind,
      provider: slot.provider,
      icon: slot.icon ?? providerIcons[slot.provider],
      seatIndex: kind === "human" ? 0 : tableSeat++
    };
  });

  const humanPlayerId = spectator ? 0 : entries.find((entry) => entry.kind === "human")?.id ?? 0;
  const playerAgents: Record<number, string> = {};
  for (const entry of entries) {
    if (entry.kind === "agent") {
      playerAgents[entry.id] = providerToAgentName[entry.provider] ?? "random";
    }
  }

  return { entries, humanPlayerId, playerAgents, numPlayers: entries.length };
}

function fromPrivateView(view: PrivateView): BoardView {
  const snapshot = view.history[view.history.length - 1];
  const winnerId =
    view.latest_phase === "GAME_OVER" && view.live_player_ids.length === 1 ? view.live_player_ids[0] : null;
  return {
    phase: snapshot.phase,
    turnId: snapshot.turn_id,
    actingPlayerId: snapshot.acting_player_id,
    pendingResponders: snapshot.pending_response_player_ids,
    pendingSelection: snapshot.pending_selection,
    pendingAction: snapshot.pending_action,
    victimId: snapshot.victim_id,
    challengerId: snapshot.challenger_id,
    blockerId: snapshot.blocker_id,
    discardPile: snapshot.discard_pile,
    deckCount: snapshot.deck_count,
    winnerId,
    players: snapshot.players,
    ownPlayerId: view.player_id,
    ownCards: snapshot.private.cards,
    legalNext: view.legal_next
  };
}

function fromObservation(view: Observation): BoardView {
  return {
    phase: view.phase,
    turnId: view.turn_id,
    actingPlayerId: view.acting_player_id,
    pendingResponders: view.pending_response_player_ids,
    pendingSelection: view.pending_selection,
    pendingAction: view.pending_action,
    victimId: view.victim_id,
    challengerId: view.challenger_id,
    blockerId: view.blocker_id,
    discardPile: view.discard_pile,
    deckCount: view.deck_count,
    winnerId: view.winner_id,
    players: view.players
  };
}

function nextActorId(view: BoardView): number | null {
  switch (view.phase) {
    case "AWAITING_ACTION":
    case "AWAITING_BLOCK_CHALLENGE":
      return view.actingPlayerId ?? null;
    case "AWAITING_CHALLENGE":
    case "AWAITING_BLOCK_OR_CHALLENGE":
      return view.pendingResponders.length > 0 ? view.pendingResponders[0] : null;
    case "AWAITING_CARD_SELECTION":
      return view.pendingSelection?.player_id ?? null;
    default:
      return null;
  }
}

function toHumanSelection(selection: LegalNext["selection"]): HumanSelection | undefined {
  if (!selection) return undefined;
  if (selection.kind === "lose_influence") {
    return { kind: "lose_influence", cards: selection.cards };
  }
  return { kind: "exchange", candidates: selection.candidates, keepCount: selection.keep_count };
}

export function GameProvider({ children }: { children: React.ReactNode }) {
  const [lobbySlots, setLobbySlots] = useState<LobbySlot[]>(defaultLobbySlots);
  const [clientSpectator, setClientSpectator] = useState(false);
  const [state, setState] = useState<GameState>(() => emptyGameState(false));

  const gameIdRef = useRef<string | null>(null);
  const rosterRef = useRef<Map<number, RosterEntry>>(new Map());
  const playerAgentsRef = useRef<Record<number, string>>({});
  const humanPlayerIdRef = useRef<number>(0);
  const spectatorRef = useRef<boolean>(false);
  const runIdRef = useRef<number>(0);
  const drivingRef = useRef<boolean>(false);
  const legalDeclarationsRef = useRef<LegalDeclaration[]>([]);
  const legalResponsesRef = useRef<ResponseName[]>([]);
  const selectedActionRef = useRef<ActionName | undefined>(undefined);

  const logStateRef = useRef<LogState>({ title: "", chosenAction: undefined, chosenTarget: undefined, blocks: [] });
  const logTurnActorRef = useRef<number | null>(null);
  const pendingNarrationRef = useRef<Narration | null>(null);
  const lastViewRef = useRef<BoardView | null>(null);
  const resetIndexRef = useRef<boolean>(false);

  const humanPlayer = state.players.find((player) => player.id === state.humanPlayerId);

  const rosterName = useCallback((id: number) => {
    if (id === humanPlayerIdRef.current) return "You";
    return rosterRef.current.get(id)?.name ?? `Player ${id}`;
  }, []);

  const turnHeader = useCallback(
    (actingPlayerId: number | null) => {
      if (actingPlayerId == null) return "";
      if (actingPlayerId === humanPlayerIdRef.current) return "Your turn.";
      return `${rosterName(actingPlayerId)}'s turn.`;
    },
    [rosterName]
  );

  const summaryLines = useCallback(
    (view: BoardView) =>
      view.players.map(
        (player) =>
          `${rosterName(player.id)}: ${player.num_coins} coin${player.num_coins === 1 ? "" : "s"}, ` +
          `${player.num_cards} card${player.num_cards === 1 ? "" : "s"}.`
      ),
    [rosterName]
  );

  const challengeOutcome = useCallback(
    (before: BoardView, after: BoardView): string[] | null => {
      const selection = after.pendingSelection;
      if (!selection || selection.kind !== "lose_influence") return null;
      const loser = selection.player_id;
      const challenger = after.challengerId;
      const claimant = before.phase === "AWAITING_BLOCK_CHALLENGE" ? after.blockerId : after.actingPlayerId;
      const winner = challenger != null && loser === challenger ? claimant : challenger;
      if (winner == null) return null;
      return [`${rosterName(winner)} has won the challenge. ${rosterName(loser)} must discard a card.`];
    },
    [rosterName]
  );

  const maybePushSummary = useCallback(
    (after: BoardView) => {
      const turnEnded =
        after.phase === "GAME_OVER" ||
        (after.actingPlayerId != null && after.actingPlayerId !== logTurnActorRef.current);
      if (!turnEnded) return;
      logStateRef.current = {
        ...logStateRef.current,
        blocks: [...logStateRef.current.blocks, summaryLines(after)]
      };
    },
    [summaryLines]
  );

  const narrate = useCallback(
    (narration: Narration, after: BoardView) => {
      const { before, decision, actorId } = narration;
      const name = rosterName(actorId);

      if (decision.command === "declare") {
        logStateRef.current = {
          title: turnHeader(actorId),
          chosenAction: decision.action,
          chosenTarget: decision.target_player_id != null ? rosterName(decision.target_player_id) : undefined,
          blocks: []
        };
        logTurnActorRef.current = actorId;
        resetIndexRef.current = true;
        maybePushSummary(after);
        return;
      }

      const blocks: string[][] = [];
      if (decision.command === "respond") {
        if (decision.response === "pass") blocks.push([`${name} passes.`]);
        else if (decision.response === "block") blocks.push([`${name} blocks.`]);
        else if (decision.response === "challenge") {
          blocks.push([`${name} challenges.`]);
          const outcome = challengeOutcome(before, after);
          if (outcome) blocks.push(outcome);
        }
      } else if (decision.command === "select_card") {
        if (decision.card) {
          const line = [`${name} discards ${decision.card}.`];
          const actor = after.players.find((player) => player.id === actorId);
          if (actor && actor.num_cards === 0) line.push(`${name} has run out of cards!`);
          blocks.push(line);
        } else if (decision.keep_cards) {
          blocks.push([`${name} exchanges influence.`]);
        }
      }

      if (blocks.length > 0) {
        logStateRef.current = { ...logStateRef.current, blocks: [...logStateRef.current.blocks, ...blocks] };
      }
      maybePushSummary(after);
    },
    [challengeOutcome, maybePushSummary, rosterName, turnHeader]
  );

  const buildPlayers = useCallback((view: BoardView, previous: Player[]): Player[] => {
    const previousById = new Map(previous.map((player) => [player.id, player]));
    const roster = [...rosterRef.current.values()].sort((a, b) => a.id - b.id);
    return roster.map((entry) => {
      const publicView = view.players.find((player) => player.id === entry.id);
      const numCards = publicView?.num_cards ?? 0;
      let cards: Influence[] = [];
      if (entry.id === view.ownPlayerId && view.ownCards) {
        cards = view.ownCards;
      } else if (publicView?.cards) {
        cards = publicView.cards;
      }
      return {
        ...entry,
        coins: publicView?.num_coins ?? 0,
        cards,
        cardCount: numCards,
        status: (publicView?.is_active ?? false) ? "active" : "spectating",
        thought: previousById.get(entry.id)?.thought
      };
    });
  }, []);

  const applyBoard = useCallback(
    (view: BoardView) => {
      if (pendingNarrationRef.current) {
        narrate(pendingNarrationRef.current, view);
        pendingNarrationRef.current = null;
      }

      const humanId = humanPlayerIdRef.current;
      const actorId = nextActorId(view);
      const humanIsNext = actorId != null && actorId === humanId;

      const isGameOver = view.winnerId != null || view.phase === "GAME_OVER";
      let phase: GameState["phase"] = "WAITING";
      if (isGameOver) {
        phase = "GAME_OVER";
      } else if (humanIsNext) {
        if (view.phase === "AWAITING_ACTION") phase = "AWAITING_ACTION";
        else if (view.phase === "AWAITING_CARD_SELECTION") phase = "AWAITING_CARD_SELECTION";
        else phase = "AWAITING_RESPONSE";
      }

      // Refresh the log at the start of the human's own action turn.
      if (view.phase === "AWAITING_ACTION" && humanIsNext && logTurnActorRef.current !== humanId) {
        logStateRef.current = { title: "Your turn.", chosenAction: undefined, chosenTarget: undefined, blocks: [] };
        logTurnActorRef.current = humanId;
        resetIndexRef.current = true;
      } else if (logTurnActorRef.current === view.actingPlayerId) {
        logStateRef.current = { ...logStateRef.current, title: turnHeader(view.actingPlayerId) };
      }

      const declarations = humanIsNext && view.legalNext ? view.legalNext.declarations : [];
      const responses = humanIsNext && view.legalNext ? view.legalNext.responses : [];
      const selection = humanIsNext && view.phase === "AWAITING_CARD_SELECTION" ? view.legalNext?.selection : null;

      legalDeclarationsRef.current = declarations;
      legalResponsesRef.current = responses;
      selectedActionRef.current = undefined;
      lastViewRef.current = view;

      const resetIndex = resetIndexRef.current;
      resetIndexRef.current = false;
      const log = logStateRef.current;

      setState((previous) => ({
        ...previous,
        phase,
        turnId: view.turnId,
        activePlayerId: view.actingPlayerId ?? 0,
        humanPlayerId: humanId,
        players: buildPlayers(view, previous.players),
        deckCount: view.deckCount,
        discardPile: view.discardPile,
        spectatorMode: spectatorRef.current,
        winnerId: view.winnerId ?? undefined,
        selectedAction: undefined,
        availableActions: declarations.map((declaration) => declaration.action),
        actionTargetIds: [],
        pendingAction: view.pendingAction ?? undefined,
        pendingTargetId: view.victimId ?? undefined,
        responseOptions: responses,
        selection: toHumanSelection(selection ?? null),
        gameLog: {
          title: log.title,
          chosenAction: log.chosenAction,
          chosenTarget: log.chosenTarget,
          blocks: log.blocks,
          blockIndex: resetIndex ? 0 : previous.gameLog.blockIndex
        }
      }));
    },
    [buildPlayers, narrate, turnHeader]
  );

  const applyAgentThought = useCallback((actorId: number, agent: AgentResult) => {
    const publicThought = agent.public_thoughts ?? agent.thoughts ?? undefined;
    const privateThought = agent.private_thoughts ?? undefined;
    if (!publicThought && !privateThought) return;
    const thought: Thought = { public: publicThought ?? "", private: privateThought ?? undefined };
    setState((previous) => ({
      ...previous,
      players: previous.players.map((player) =>
        player.id === actorId ? { ...player, thought } : { ...player, thought: undefined }
      )
    }));
  }, []);

  const handleError = useCallback((error: unknown) => {
    runIdRef.current += 1;
    drivingRef.current = false;
    const message =
      error instanceof ApiError ? error.detail ?? error.message : error instanceof Error ? error.message : String(error);
    setState((previous) => ({ ...previous, phase: "WAITING", errorMessage: message }));
  }, []);

  const fetchBoard = useCallback(async (gameId: string): Promise<BoardView> => {
    if (spectatorRef.current || humanPlayerIdRef.current === 0) {
      return fromObservation(await apiClient.observation(gameId, true));
    }
    return fromPrivateView(await apiClient.privateView(gameId, humanPlayerIdRef.current));
  }, []);

  const drive = useCallback(async () => {
    if (drivingRef.current) return;
    drivingRef.current = true;
    const myRun = runIdRef.current;
    try {
      while (runIdRef.current === myRun) {
        const gameId = gameIdRef.current;
        if (!gameId) break;

        let view: BoardView;
        try {
          view = await fetchBoard(gameId);
        } catch (error) {
          if (!isAbort(error)) handleError(error);
          return;
        }
        if (runIdRef.current !== myRun) return;

        applyBoard(view);

        if (view.winnerId != null || view.phase === "GAME_OVER") return;

        const actorId = nextActorId(view);
        if (actorId == null) return;
        if (actorId === humanPlayerIdRef.current) return;

        const agentName = playerAgentsRef.current[actorId] ?? "random";
        let result;
        try {
          result = await apiClient.agentAct(gameId, agentName, actorId);
        } catch (error) {
          if (!isAbort(error)) handleError(error);
          return;
        }
        if (runIdRef.current !== myRun) return;

        applyAgentThought(actorId, result.agent);
        pendingNarrationRef.current = { before: view, decision: result.agent.decision, actorId };

        await delay(PACING_MS);
      }
    } finally {
      drivingRef.current = false;
    }
  }, [applyAgentThought, applyBoard, fetchBoard, handleError]);

  const dispatchHuman = useCallback(
    (decision: AgentDecision, perform: () => Promise<unknown>) => {
      const gameId = gameIdRef.current;
      if (!gameId) return;
      const before = lastViewRef.current;
      setState((previous) => ({
        ...previous,
        phase: "WAITING",
        selectedAction: undefined,
        availableActions: [],
        actionTargetIds: [],
        responseOptions: [],
        selection: undefined
      }));
      legalDeclarationsRef.current = [];
      legalResponsesRef.current = [];
      selectedActionRef.current = undefined;
      (async () => {
        try {
          await perform();
        } catch (error) {
          if (!isAbort(error)) handleError(error);
          return;
        }
        if (before) {
          pendingNarrationRef.current = { before, decision, actorId: humanPlayerIdRef.current };
        }
        drive();
      })();
    },
    [drive, handleError]
  );

  const declareHuman = useCallback(
    (action: ActionName, targetId?: number) => {
      const gameId = gameIdRef.current;
      if (!gameId) return;
      dispatchHuman(
        { command: "declare", action, target_player_id: targetId },
        () => apiClient.declareAction(gameId, humanPlayerIdRef.current, action, targetId)
      );
    },
    [dispatchHuman]
  );

  const chooseCoupTarget = useCallback(
    (targetIds: number[]): number | undefined => {
      const players = new Map(state.players.map((player) => [player.id, player]));
      return [...targetIds]
        .sort((a, b) => {
          const pa = players.get(a);
          const pb = players.get(b);
          return (pb?.cardCount ?? 0) - (pa?.cardCount ?? 0) || (pb?.coins ?? 0) - (pa?.coins ?? 0) || a - b;
        })
        .at(0);
    },
    [state.players]
  );

  const value: GameContextValue = {
    lobbySlots,
    clientSpectator,
    state,
    humanPlayer,
    availableActions: state.availableActions,
    addAgent(slotId) {
      setLobbySlots((slots) => {
        const used = slots.filter((slot) => slot.provider !== "empty").length;
        const next = agentCycle[(used - 1) % agentCycle.length];
        return slots.map((slot) =>
          slot.id === slotId
            ? { id: slot.id, name: next.name, provider: next.provider, icon: providerIcons[next.provider] }
            : slot
        );
      });
    },
    removeAgent(slotId) {
      setLobbySlots((slots) => slots.map((slot) => (slot.id === slotId ? { id: slot.id, name: "", provider: "empty" } : slot)));
    },
    setClientSpectator(nextValue) {
      setClientSpectator(nextValue);
    },
    beginGame() {
      const { entries, humanPlayerId, playerAgents, numPlayers } = buildRoster(lobbySlots, clientSpectator);
      rosterRef.current = new Map(entries.map((entry) => [entry.id, entry]));
      playerAgentsRef.current = playerAgents;
      humanPlayerIdRef.current = humanPlayerId;
      spectatorRef.current = clientSpectator;
      legalDeclarationsRef.current = [];
      legalResponsesRef.current = [];
      selectedActionRef.current = undefined;
      logStateRef.current = { title: "", chosenAction: undefined, chosenTarget: undefined, blocks: [] };
      logTurnActorRef.current = null;
      pendingNarrationRef.current = null;
      lastViewRef.current = null;
      resetIndexRef.current = false;
      runIdRef.current += 1;
      drivingRef.current = false;

      setState({
        ...emptyGameState(clientSpectator),
        phase: "WAITING",
        humanPlayerId,
        players: entries.map((entry) => ({
          ...entry,
          coins: 0,
          cards: [],
          cardCount: 0,
          status: "active" as const
        }))
      });

      (async () => {
        try {
          const summary = await apiClient.createGame(numPlayers, playerAgents);
          gameIdRef.current = summary.game_id;
        } catch (error) {
          if (!isAbort(error)) handleError(error);
          return;
        }
        drive();
      })();
    },
    leaveGame() {
      runIdRef.current += 1;
      drivingRef.current = false;
      gameIdRef.current = null;
      rosterRef.current = new Map();
      logStateRef.current = { title: "", chosenAction: undefined, chosenTarget: undefined, blocks: [] };
      logTurnActorRef.current = null;
      pendingNarrationRef.current = null;
      lastViewRef.current = null;
      setState(emptyGameState(clientSpectator));
    },
    selectAction(action) {
      const declaration = legalDeclarationsRef.current.find((entry) => entry.action === action);
      if (!declaration) return;
      if (declaration.requires_target) {
        selectedActionRef.current = action;
        setState((previous) => ({
          ...previous,
          phase: "AWAITING_TARGET",
          selectedAction: action,
          actionTargetIds: declaration.valid_target_ids
        }));
        return;
      }
      declareHuman(action);
    },
    selectTarget(targetId) {
      const action = selectedActionRef.current;
      if (!action) return;
      selectedActionRef.current = undefined;
      declareHuman(action, targetId);
    },
    submitResponse(response) {
      const gameId = gameIdRef.current;
      if (!gameId) return;
      if (!legalResponsesRef.current.includes(response)) return;
      dispatchHuman(
        { command: "respond", response },
        () => apiClient.respond(gameId, humanPlayerIdRef.current, response)
      );
    },
    selectInfluence(card) {
      const gameId = gameIdRef.current;
      if (!gameId) return;
      dispatchHuman(
        { command: "select_card", card },
        () => apiClient.selectCard(gameId, humanPlayerIdRef.current, { card })
      );
    },
    selectExchange(keepCards) {
      const gameId = gameIdRef.current;
      if (!gameId) return;
      dispatchHuman(
        { command: "select_card", keep_cards: keepCards },
        () => apiClient.selectCard(gameId, humanPlayerIdRef.current, { keep_cards: keepCards })
      );
    },
    clearError() {
      setState((previous) => ({ ...previous, errorMessage: undefined }));
    }
  };

  // Reveal game-log blocks one at a time.
  useEffect(() => {
    const { blocks, blockIndex } = state.gameLog;
    if (blockIndex >= blocks.length - 1) return;
    const timeout = window.setTimeout(() => {
      setState((current) => ({
        ...current,
        gameLog: {
          ...current.gameLog,
          blockIndex: Math.min(current.gameLog.blockIndex + 1, current.gameLog.blocks.length - 1)
        }
      }));
    }, BLOCK_REVEAL_MS);
    return () => window.clearTimeout(timeout);
  }, [state.gameLog.blockIndex, state.gameLog.blocks.length]);

  // Fade agent thoughts out after they have been on screen for a few seconds.
  useEffect(() => {
    if (!state.players.some((player) => player.thought)) return;
    const timeout = window.setTimeout(() => {
      setState((current) => ({
        ...current,
        players: current.players.map((player) => ({ ...player, thought: undefined }))
      }));
    }, 7000);
    return () => window.clearTimeout(timeout);
  }, [state.turnId, state.phase, state.players]);

  // Human action timeout: fall back to Income, or a forced Coup at the coin limit.
  useEffect(() => {
    if (state.phase !== "AWAITING_ACTION") return;
    const timeout = window.setTimeout(() => {
      const declarations = legalDeclarationsRef.current;
      const income = declarations.find((entry) => entry.action === "Income");
      if (income) {
        declareHuman("Income");
        return;
      }
      const coup = declarations.find((entry) => entry.action === "Coup");
      if (coup) {
        declareHuman("Coup", chooseCoupTarget(coup.valid_target_ids));
        return;
      }
      const fallback = declarations[0];
      if (fallback) {
        declareHuman(
          fallback.action,
          fallback.requires_target ? chooseCoupTarget(fallback.valid_target_ids) : undefined
        );
      }
    }, 60000);
    return () => window.clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.turnId, state.activePlayerId]);

  // Human response timeout: fall back to a pass.
  useEffect(() => {
    if (state.phase !== "AWAITING_RESPONSE") return;
    const timeout = window.setTimeout(() => {
      const gameId = gameIdRef.current;
      if (!gameId || !legalResponsesRef.current.includes("pass")) return;
      dispatchHuman(
        { command: "respond", response: "pass" },
        () => apiClient.respond(gameId, humanPlayerIdRef.current, "pass")
      );
    }, 10000);
    return () => window.clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.turnId, state.pendingAction]);

  // Human card-selection timeout: pick a safe default so the game never stalls.
  useEffect(() => {
    if (state.phase !== "AWAITING_CARD_SELECTION" || !state.selection) return;
    const selection = state.selection;
    const timeout = window.setTimeout(() => {
      const gameId = gameIdRef.current;
      if (!gameId) return;
      if (selection.kind === "lose_influence" && selection.cards?.length) {
        const card = selection.cards[0];
        dispatchHuman({ command: "select_card", card }, () =>
          apiClient.selectCard(gameId, humanPlayerIdRef.current, { card })
        );
      } else if (selection.kind === "exchange" && selection.candidates && selection.keepCount != null) {
        const keep = selection.candidates.slice(0, selection.keepCount);
        dispatchHuman({ command: "select_card", keep_cards: keep }, () =>
          apiClient.selectCard(gameId, humanPlayerIdRef.current, { keep_cards: keep })
        );
      }
    }, 20000);
    return () => window.clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.turnId, state.selection]);

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}

export function useGame() {
  const context = useContext(GameContext);
  if (!context) throw new Error("useGame must be used inside GameProvider");
  return context;
}
