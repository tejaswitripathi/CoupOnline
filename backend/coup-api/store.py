import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coup-core"))

from action import ALL_ACTIONS
from player import Player
from resolver import Resolver
from state import State
from state_stack import StateStack


DEFAULT_GAME_ID = "default"


@dataclass
class GameRecord:
    id: str
    state_stack: StateStack
    resolver: Resolver
    player_agents: dict[int, str] = field(default_factory=dict)

    def latest_state(self) -> State:
        return self.state_stack.get_states()[-1]


class GameDatabase:
    def __init__(self):
        self.games: dict[str, GameRecord] = {}
        self.create_game(game_id=DEFAULT_GAME_ID)

    def create_game(
        self,
        game_id: str | None = None,
        num_players: int = 4,
        player_agents: dict[int, str] | None = None,
    ) -> GameRecord:
        assert 2 <= num_players <= 4, "Coup supports 2 to 4 players in this implementation."

        game_id = game_id or str(uuid4())
        players = [Player(i + 1) for i in range(num_players)]
        initial_state = State(players, turn_id=0, deck=None, phase=None)
        record = GameRecord(
            id=game_id,
            state_stack=StateStack(states=[initial_state]),
            resolver=Resolver(),
            player_agents=player_agents or {},
        )
        self.games[game_id] = record
        return record

    def delete_game(self, game_id: str) -> None:
        assert game_id in self.games, f"Unknown game_id: {game_id}"
        del self.games[game_id]

    def get_game(self, game_id: str | None = None) -> GameRecord:
        game_id = game_id or DEFAULT_GAME_ID
        assert game_id in self.games, f"Unknown game_id: {game_id}"
        return self.games[game_id]

    def list_games(self) -> list[dict]:
        return [self.game_summary(record.id) for record in self.games.values()]

    def game_summary(self, game_id: str | None = None) -> dict:
        record = self.get_game(game_id)
        state = record.latest_state()
        live_player_ids = [p.id for p in state.players if len(p.cards) > 0]
        return {
            "game_id": record.id,
            "turn_id": state.turn_id,
            "phase": state.phase,
            "acting_player_id": getattr(state, "acting_player_id", None),
            "live_player_ids": live_player_ids,
            "winner_id": live_player_ids[0] if state.phase == "GAME_OVER" and len(live_player_ids) == 1 else None,
            "num_states": len(record.state_stack.get_states()),
            "player_agents": dict(record.player_agents),
        }

    def _copy_latest_state(self, record: GameRecord) -> State:
        return copy.deepcopy(record.latest_state())

    def _push_state(self, record: GameRecord, state: State) -> State:
        record.state_stack.add_state(state)
        return state

    def _resolve_and_push(self, record: GameRecord, state: State, action_name: str) -> State:
        state.phase = "RESOLVING"
        resolver_payload = {
            "state": state,
            "action": ALL_ACTIONS[action_name],
            "blocked": getattr(state, "blocked", 0),
            "challenged": getattr(state, "challenged", 0),
            "victim_id": getattr(state, "victim_id", None),
            "challenger_id": getattr(state, "challenger_id", None),
            "blocker_id": getattr(state, "blocker_id", None),
        }
        return self._push_state(record, record.resolver.generate_next_state(resolver_payload))

    def _response_player_ids(self, state: State, action_name: str) -> set[int]:
        if action_name in ("Steal", "Assassinate"):
            victim_id = getattr(state, "victim_id", None)
            return {victim_id} if victim_id is not None else set()

        return {
            p.id for p in state.players
            if p.id != state.acting_player_id and len(p.cards) > 0
        }

    def _card_name(self, card) -> str:
        return card.name if hasattr(card, "name") else card

    def _player_has_card(self, player: Player, card_name: str) -> bool:
        return any(self._card_name(card) == card_name for card in player.cards)

    def _is_challengeable(self, record: GameRecord, action_name: str) -> bool:
        return (
            action_name in record.resolver.ACTION_CLAIMS
            or action_name in record.resolver.FORBIDDEN_ACTION_CLAIMS
        )

    def resolve_action(self, game_id: str | None, payload: dict) -> State:
        record = self.get_game(game_id)
        action_name = payload.get("action")
        assert action_name in ALL_ACTIONS, f"Unknown action: {action_name}"

        state = self._copy_latest_state(record)
        state.blocked = payload.get("blocked", 0)
        state.challenged = payload.get("challenged", 0)
        if "victim_id" in payload:
            state.victim_id = payload["victim_id"]
        state.challenger_id = payload.get("challenger_id")
        state.blocker_id = payload.get("blocker_id")
        state.pending_action = action_name

        return self._resolve_and_push(record, state, action_name)

    def declare_action(self, game_id: str | None, payload: dict) -> State:
        record = self.get_game(game_id)
        state = self._copy_latest_state(record)

        assert state.phase == "AWAITING_ACTION", f"Not awaiting an action; phase is {state.phase}"

        player_id = payload.get("player_id")
        assert player_id == state.acting_player_id, "It is not this player's turn"

        action_name = payload.get("action")
        assert action_name in ALL_ACTIONS, f"Unknown action: {action_name}"

        action = ALL_ACTIONS[action_name]
        blockable = action_name in record.resolver.BLOCK_CLAIMS
        challengeable = self._is_challengeable(record, action_name)
        targeted = action_name in record.resolver.TARGETED_ACTIONS

        players = state.get_players_dict()
        player = players[player_id]
        if player.num_coins >= 10:
            assert action_name == "Coup", "A player with 10 or more coins must coup."
        if action_name == "Coup":
            assert player.num_coins >= 7, "Player needs at least 7 coins to coup."
        if action_name == "Assassinate":
            assert player.num_coins >= 3, "Player needs at least 3 coins to assassinate."
        if action_name == "Foreign Aid":
            assert not self._player_has_card(player, "Duke"), "Players holding Duke cannot take Foreign Aid."

        if targeted:
            target_id = payload.get("target_player_id")
            assert target_id in players, f"Unknown target_player_id: {target_id}"
            assert target_id != player_id, "A player cannot target themselves."
            assert len(players[target_id].cards) > 0, "Cannot target an eliminated player."
            state.victim_id = target_id
        else:
            state.victim_id = None

        state.pending_action = action_name
        state.blocked = 0
        state.challenged = 0
        state.challenger_id = None
        state.blocker_id = None
        state.pending_selections = []

        if not (blockable or challengeable):
            return self._resolve_and_push(record, state, action.name)

        state.pending_responses = self._response_player_ids(state, action_name)
        state.phase = "AWAITING_BLOCK_OR_CHALLENGE" if blockable else "AWAITING_CHALLENGE"
        return self._push_state(record, state)

    def _can_block(self, state: State, player_id: int) -> bool:
        if getattr(state, "pending_action", None) in ("Steal", "Assassinate"):
            return player_id == getattr(state, "victim_id", None)
        return True

    def respond_to_action(self, game_id: str | None, payload: dict) -> State:
        record = self.get_game(game_id)
        state = self._copy_latest_state(record)

        assert state.phase in (
            "AWAITING_CHALLENGE",
            "AWAITING_BLOCK_OR_CHALLENGE",
            "AWAITING_BLOCK_CHALLENGE",
        ), f"Not awaiting a response; phase is {state.phase}"

        player_id = payload.get("player_id")
        response = payload.get("response")
        action_name = state.pending_action
        assert action_name in ALL_ACTIONS, "No pending action to respond to."

        if state.phase == "AWAITING_BLOCK_CHALLENGE":
            assert player_id == state.acting_player_id, "Only the acting player may respond to a block"
            if response == "challenge":
                state.challenged = 1
                state.challenger_id = player_id
            else:
                assert response == "pass", f"Invalid response for this phase: {response}"
            return self._resolve_and_push(record, state, action_name)

        assert player_id in state.pending_responses, "Player is not eligible to respond right now"

        if response == "challenge":
            assert self._is_challengeable(record, action_name), f"{action_name} cannot be challenged"
            state.challenged = 1
            state.challenger_id = player_id
            state.pending_responses = set()
            return self._resolve_and_push(record, state, action_name)

        if response == "block":
            assert action_name in record.resolver.BLOCK_CLAIMS, f"{action_name} cannot be blocked"
            assert self._can_block(state, player_id), f"Player {player_id} cannot block {action_name}"
            state.blocked = 1
            state.blocker_id = player_id
            state.pending_responses = set()
            state.phase = "AWAITING_BLOCK_CHALLENGE"
            return self._push_state(record, state)

        if response == "pass":
            state.pending_responses.discard(player_id)
            if not state.pending_responses:
                return self._resolve_and_push(record, state, action_name)
            return self._push_state(record, state)

        raise AssertionError(f"Invalid response: {response}")

    def select_card(self, game_id: str | None, payload: dict) -> State:
        record = self.get_game(game_id)
        state = self._copy_latest_state(record)
        assert state.phase == "AWAITING_CARD_SELECTION", f"No card selection pending; phase is {state.phase}"
        return self._push_state(record, record.resolver.apply_selection({"state": state, **payload}))

    def dispatch_decision(self, game_id: str | None, player_id: int, decision: dict) -> State:
        command = decision["command"]
        if command == "declare":
            payload = {"player_id": player_id, "action": decision["action"]}
            if "target_player_id" in decision:
                payload["target_player_id"] = decision["target_player_id"]
            return self.declare_action(game_id, payload)
        if command == "respond":
            return self.respond_to_action(game_id, {"player_id": player_id, "response": decision["response"]})
        if command == "select_card":
            payload = {"player_id": player_id}
            if "card" in decision:
                payload["card"] = decision["card"]
            if "keep_cards" in decision:
                payload["keep_cards"] = decision["keep_cards"]
            return self.select_card(game_id, payload)
        if command == "noop":
            return self.latest_state(game_id)
        raise AssertionError(f"Unknown agent command: {command}")

    def latest_state(self, game_id: str | None = None) -> State:
        return self.get_game(game_id).latest_state()

    def private_view(self, game_id: str | None, player_id: int) -> dict:
        return self.get_game(game_id).state_stack.private_view({"player_id": player_id})


GAME_DB = GameDatabase()

# Backward-compatible handles for older code/tests.
STATE_STACK = GAME_DB.get_game(DEFAULT_GAME_ID).state_stack
RESOLVER = GAME_DB.get_game(DEFAULT_GAME_ID).resolver
