from state import State


class StateStack():

    def __init__(self, states: list[State]):
        self.states = states

    def get_states(self) -> list[State]:
        return self.states
    
    def get_states_dict(self) -> dict:
        state_dict = {}
        for s in self.states:
            if s.turn_id in state_dict:
                state_dict[s.turn_id].append(s)
            else:
                state_dict[s.turn_id] = [s]
        return state_dict

    def add_state(self, state: State) -> None:
        self.states.append(state)

    def _card_name(self, card) -> str:
        return card.name if hasattr(card, "name") else card

    def _live_player_ids(self, state: State) -> list[int]:
        return [p.id for p in state.players if len(p.cards) > 0]

    def _target_ids(self, state: State, player_id: int) -> list[int]:
        return [p.id for p in state.players if p.id != player_id and len(p.cards) > 0]

    def _public_player_view(self, player) -> dict:
        return {
            "id": player.id,
            "num_coins": player.num_coins,
            "num_cards": len(player.cards),
            "is_active": len(player.cards) > 0,
        }

    def _player_has_card(self, player, card_name: str) -> bool:
        return any(self._card_name(card) == card_name for card in player.cards)

    def _pending_selection_for_player(self, state: State, player_id: int):
        selections = getattr(state, "pending_selections", [])
        if not selections:
            return None

        selection = selections[0]
        if selection.get("player_id") != player_id:
            return {
                "kind": selection.get("kind"),
                "player_id": selection.get("player_id"),
            }

        view = dict(selection)
        view.pop("prefer_object", None)
        return view

    def _legal_declarations(self, state: State, player_id: int) -> list[dict]:
        player = state.get_players_dict().get(player_id)
        if not player or state.phase != "AWAITING_ACTION" or state.acting_player_id != player_id:
            return []

        actions = []
        target_ids = self._target_ids(state, player_id)

        def add_action(name: str, requires_target: bool = False) -> None:
            actions.append({
                "action": name,
                "requires_target": requires_target,
                "valid_target_ids": target_ids if requires_target else [],
            })

        if player.num_coins >= 10:
            if player.num_coins >= 7:
                add_action("Coup", True)
            return actions

        add_action("Income")
        if not self._player_has_card(player, "Duke"):
            add_action("Foreign Aid")
        add_action("Tax")
        add_action("Exchange")
        add_action("Steal", True)
        if player.num_coins >= 3:
            add_action("Assassinate", True)
        if player.num_coins >= 7:
            add_action("Coup", True)

        return actions

    def _legal_responses(self, state: State, player_id: int) -> list[str]:
        if state.phase == "AWAITING_BLOCK_CHALLENGE":
            return ["pass", "challenge"] if player_id == state.acting_player_id else []

        if state.phase not in ("AWAITING_CHALLENGE", "AWAITING_BLOCK_OR_CHALLENGE"):
            return []

        pending_responses = getattr(state, "pending_responses", set())
        if player_id not in pending_responses:
            return []

        responses = ["pass"]
        if state.phase in ("AWAITING_CHALLENGE", "AWAITING_BLOCK_OR_CHALLENGE"):
            responses.append("challenge")
        if (
            state.phase == "AWAITING_BLOCK_OR_CHALLENGE"
            and (
                getattr(state, "pending_action", None) not in ("Steal", "Assassinate")
                or player_id == getattr(state, "victim_id", None)
            )
        ):
            responses.append("block")
        return responses

    def _legal_selection(self, state: State, player_id: int):
        selection = self._pending_selection_for_player(state, player_id)
        if not selection or selection.get("player_id") != player_id:
            return None

        if selection["kind"] == "lose_influence":
            player = state.get_players_dict()[player_id]
            return {
                "kind": "lose_influence",
                "cards": [self._card_name(card) for card in player.cards],
            }

        if selection["kind"] == "exchange":
            return {
                "kind": "exchange",
                "candidates": list(selection["candidates"]),
                "keep_count": selection["keep_count"],
            }

        return selection

    def _snapshot_for_player(self, state: State, player_id: int) -> dict:
        players = state.get_players_dict()
        player = players[player_id]

        return {
            "turn_id": state.turn_id,
            "phase": state.phase,
            "acting_player_id": getattr(state, "acting_player_id", None),
            "victim_id": getattr(state, "victim_id", None),
            "pending_action": getattr(state, "pending_action", None),
            "blocked": getattr(state, "blocked", 0),
            "challenged": getattr(state, "challenged", 0),
            "challenger_id": getattr(state, "challenger_id", None),
            "blocker_id": getattr(state, "blocker_id", None),
            "pending_response_player_ids": sorted(list(getattr(state, "pending_responses", set()))),
            "pending_selection": self._pending_selection_for_player(state, player_id),
            "discard_pile": list(getattr(state, "discard_pile", [])),
            "deck_count": len(state.deck or []),
            "players": [self._public_player_view(p) for p in state.players],
            "private": {
                "player_id": player_id,
                "cards": [self._card_name(card) for card in player.cards],
            },
        }

    def private_view(self, payload: dict) -> dict:
        player_id = payload["player_id"]

        if not self.states:
            raise AssertionError("No game states are available.")

        latest_state = self.states[-1]
        players = latest_state.get_players_dict()
        assert player_id in players, f"Unknown player_id: {player_id}"

        return {
            "player_id": player_id,
            "latest_turn_id": latest_state.turn_id,
            "latest_phase": latest_state.phase,
            "live_player_ids": self._live_player_ids(latest_state),
            "history": [self._snapshot_for_player(state, player_id) for state in self.states],
            "legal_next": {
                "declarations": self._legal_declarations(latest_state, player_id),
                "responses": self._legal_responses(latest_state, player_id),
                "selection": self._legal_selection(latest_state, player_id),
            },
        }
