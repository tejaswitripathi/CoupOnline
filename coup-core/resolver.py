import copy
import random

from state import State
from action import Action, ALL_ACTIONS
from card import ALL_CARDS
from player import Player


class Resolver():

    ACTION_CLAIMS = {
        "Tax": {"Duke"},
        "Steal": {"Captain"},
        "Assassinate": {"Assassin"},
        "Exchange": {"Ambassador"},
    }

    BLOCK_CLAIMS = {
        "Foreign Aid": {"Duke"},
        "Steal": {"Captain", "Ambassador"},
        "Assassinate": {"Contessa"},
    }

    TARGETED_ACTIONS = {"Coup", "Steal", "Assassinate"}

    def __init__(self):
        pass

    def _ensure_state_shape(self, state: State) -> None:
        if not hasattr(state, "discard_pile"):
            state.discard_pile = []
        if not hasattr(state, "victim_id"):
            state.victim_id = None
        state.num_cards_per_player = {p.id: len(p.cards) for p in state.players}

    def _card_name(self, card) -> str:
        return card.name if hasattr(card, "name") else card

    def _card_for_player(self, player: Player, card_name: str, prefer_object: bool | None = None):
        if prefer_object is None:
            prefer_object = any(hasattr(card, "name") for card in player.cards)
        return ALL_CARDS[card_name] if prefer_object else card_name

    def _find_card(self, player: Player, card_names: set[str]):
        for card in player.cards:
            if self._card_name(card) in card_names:
                return card
        return None

    def _player_has_claim(self, player: Player, card_names: set[str]) -> bool:
        return self._find_card(player, card_names) is not None

    def _lose_influence(self, state: State, player: Player, card=None):
        if not player.cards:
            return None

        lost_card = player.remove_card(card)
        lost_card_name = self._card_name(lost_card)
        state.discard_pile.append(lost_card_name)
        state.num_cards_per_player[player.id] = len(player.cards)
        return lost_card

    def _reveal_and_replace(self, state: State, player: Player, card_names: set[str]) -> None:
        revealed_card = self._find_card(player, card_names)
        assert revealed_card is not None, "Player does not have the claimed card."

        was_object = hasattr(revealed_card, "name")
        revealed_card_name = self._card_name(revealed_card)
        player.remove_card(revealed_card)
        state.shuffle_card(revealed_card_name)

        replacement_name = state.draw_card()
        player.add_card(self._card_for_player(player, replacement_name, was_object))
        state.num_cards_per_player[player.id] = len(player.cards)

    def _active_players(self, state: State) -> list[Player]:
        return [p for p in state.players if len(p.cards) > 0]

    def num_active_players(self, num_cards_per_player):
        return sum(1 for count in num_cards_per_player.values() if count > 0)

    def base_state_builder(self, state: State) -> State:
        self._ensure_state_shape(state)
        state.turn_id += 1

        active_players = self._active_players(state)
        if len(active_players) <= 1:
            state.phase = "GAME_OVER"
            state.victim_id = None
            return state

        current_index = next(
            (i for i, player in enumerate(state.players) if player.id == state.acting_player_id),
            -1,
        )
        for offset in range(1, len(state.players) + 1):
            candidate = state.players[(current_index + offset) % len(state.players)]
            if len(candidate.cards) > 0:
                state.acting_player_id = candidate.id
                break

        state.victim_id = None
        state.phase = "AWAITING_ACTION"
        return state

    def _pay_for_action_attempt(self, action: Action, attacker: Player) -> None:
        if action.name == "Coup":
            assert attacker.num_coins >= 7, "Player needs at least 7 coins to coup."
            attacker.num_coins -= 7
        elif action.name == "Assassinate":
            assert attacker.num_coins >= 3, "Player needs at least 3 coins to assassinate."
            attacker.num_coins -= 3

    def _exchange(self, state: State, player: Player, payload: dict | None = None) -> None:
        hand_size = len(player.cards)
        if hand_size == 0:
            return

        prefer_object = any(hasattr(card, "name") for card in player.cards)
        drawn_cards = [
            self._card_for_player(player, state.draw_card(), prefer_object)
            for _ in range(min(2, len(state.deck)))
        ]
        available_cards = list(player.cards) + drawn_cards

        keep_names = None
        if payload:
            keep_names = payload.get("exchange_keep_cards") or payload.get("keep_cards")

        keep_indices = set()
        if keep_names:
            keep_names = list(keep_names)
            for keep_name in keep_names:
                for index, card in enumerate(available_cards):
                    if index not in keep_indices and self._card_name(card) == keep_name:
                        keep_indices.add(index)
                        break
            assert len(keep_indices) == hand_size, "Exchange must keep one card per remaining influence."
        else:
            keep_indices = set(random.sample(range(len(available_cards)), hand_size))

        kept_cards = [card for index, card in enumerate(available_cards) if index in keep_indices]
        returned_cards = [card for index, card in enumerate(available_cards) if index not in keep_indices]
        player.cards = kept_cards
        for card in returned_cards:
            state.shuffle_card(self._card_name(card))

        state.num_cards_per_player[player.id] = len(player.cards)

    def resolve_actions(self, action, player_a, player_b, state, payload: dict | None = None):
        if action.name == "Income":
            player_a.num_coins += 1
        elif action.name == "Foreign Aid":
            player_a.num_coins += 2
        elif action.name == "Tax":
            player_a.num_coins += 3
        elif action.name == "Coup":
            self._lose_influence(state, player_b)
        elif action.name == "Assassinate":
            self._lose_influence(state, player_b)
        elif action.name == "Steal":
            stolen_coins = min(2, player_b.num_coins)
            player_b.num_coins -= stolen_coins
            player_a.num_coins += stolen_coins
        elif action.name == "Exchange":
            self._exchange(state, player_a, payload)

        return

    def _get_player(self, players_dict: dict[int, Player], player_id: int | None, role: str) -> Player:
        assert player_id is not None, f"{role} is required for this resolution."
        assert player_id in players_dict, f"Unknown {role}: {player_id}"
        return players_dict[player_id]

    def generate_next_state(self, payload: dict) -> State:

        # Payload:
        # - state: State
        # - action: Action
        # - blocked: 1 | 0
        # - challenged: 1 | 0
        # Optional IDs for richer clients:
        # - victim_id: target of Coup/Steal/Assassinate
        # - challenger_id: player challenging the acting player's claim
        # - blocker_id: player claiming the block

        state = copy.deepcopy(payload["state"])
        self._ensure_state_shape(state)
        assert state.phase == "RESOLVING", f"State must be in phase RESOLVING; found state: {state.phase}"

        action = payload["action"]
        players_dict = state.get_players_dict()
        acting_player_id = state.acting_player_id
        victim_id = payload.get("victim_id", state.victim_id)
        blocked = bool(payload.get("blocked", 0))
        challenged = bool(payload.get("challenged", 0))
        challenger_id = payload.get("challenger_id")
        if challenger_id is None:
            challenger_id = acting_player_id if blocked and challenged else victim_id
        blocker_id = payload.get("blocker_id", victim_id)

        attacker = self._get_player(players_dict, acting_player_id, "acting_player_id")
        victim = (
            self._get_player(players_dict, victim_id, "victim_id")
            if action.name in self.TARGETED_ACTIONS
            else None
        )

        assert len(attacker.cards) > 0, "Eliminated players cannot act."
        if victim is not None:
            assert victim.id != attacker.id, "A player cannot target themselves."
            assert len(victim.cards) > 0, "Cannot target an eliminated player."
        if attacker.num_coins >= 10 and action.name != "Coup":
            raise AssertionError("A player with 10 or more coins must coup.")

        self._pay_for_action_attempt(action, attacker)

        if blocked:
            assert action.name in self.BLOCK_CLAIMS, f"{action.name} cannot be blocked."
            if challenged:
                blocker = self._get_player(players_dict, blocker_id, "blocker_id")
                block_claims = self.BLOCK_CLAIMS[action.name]

                if self._player_has_claim(blocker, block_claims):
                    challenger = self._get_player(players_dict, challenger_id, "challenger_id")
                    self._lose_influence(state, challenger)
                    self._reveal_and_replace(state, blocker, block_claims)
                    return self.base_state_builder(state)

                self._lose_influence(state, blocker)
                self.resolve_actions(action, attacker, victim, state, payload)
                return self.base_state_builder(state)

            return self.base_state_builder(state)

        if challenged:
            action_claims = self.ACTION_CLAIMS.get(action.name)
            assert action_claims is not None, f"{action.name} cannot be challenged."
            challenger = self._get_player(players_dict, challenger_id, "challenger_id")

            if self._player_has_claim(attacker, action_claims):
                self._lose_influence(state, challenger)
                self._reveal_and_replace(state, attacker, action_claims)
                self.resolve_actions(action, attacker, victim, state, payload)
                return self.base_state_builder(state)

            self._lose_influence(state, attacker)
            return self.base_state_builder(state)

        self.resolve_actions(action, attacker, victim, state, payload)
        return self.base_state_builder(state)
