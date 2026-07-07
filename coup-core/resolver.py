from state import State
from action import Action, ALL_ACTIONS
from card import ALL_CARDS

class Resolver():

    def __init__(self):
        pass

    def generate_next_state(self, payload: dict) -> State:
        
        # Payload:
        # - state: State
        # - action: Action
        # - blocked: 1 | 0
        # - challenged: 1 | 0

        state = payload["state"]
        action = payload["action"]
        parent_cards = action.parent_cards
        players = state.players
        players_dict = state.get_players_dict()
        acting_player_id = state.acting_player_id
        victim_id = state.victim_id
        
        if payload["blocked"] and payload["challenged"]:
            victim = players_dict[victim_id]
            attacker = players_dict[acting_player_id]
            blockables = victim.get_all_blockables()

            if action in blockables:
                attacker.remove_card()

                old_card = list(parent_cards & victim.cards)[0]
                victim.remove_card(old_card)
                state.shuffle_card(old_card.name)

                new_card = state.draw_card()
                new_card = ALL_CARDS[new_card]
                victim.add_card(new_card)
            
            
