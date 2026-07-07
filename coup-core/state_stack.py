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

    def add_state(self, state: State) -> None:
        self.states.append(state)

    def private_view(self, payload: dict) -> dict:
        player_id = payload["player_id"]
        action = payload["action"].name
        blocked = payload["blocked"]
        challenged = payload["challenged"]

        players = self.state.get_players_dict()

        view_for_player = {}
        for state in self.states:
            state_id = (state.turn_id, state.phase)
            
            view_for_player[state_id] = {
                "card_counts": {p.id: len(p.cards) for p in state.players},
                "player_cards": [c.name for c in players[player_id].cards],     # concern: player cards may not freeze, past state may point to updated player cards since player objects are separate
                "acting_player_id": state.acting_player_id,
                "victim_id": state.victim_id,
                "discard_pile": state.discard_pile,
                "action": action,
                "blocked": blocked,
                "challenged": challenged
            }
        