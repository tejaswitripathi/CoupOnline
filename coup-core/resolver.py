from state import State
from action import Action, ALL_ACTIONS
from card import ALL_CARDS

class Resolver():

    def __init__(self):
        pass

    def resolve_actions(self, action, player_a, player_b):
        player_a.num_coins -= action.cost

        if action.name in ["Coup", "Assasinate"]:
            player_b.remove_card()

        elif action.name == "Steal":
            player_b.num_coins += action.cost

    def num_active_players(self, num_cards_per_player):
        count = 0
        for id in num_cards_per_player:
            if num_cards_per_player[id] > 0:
                count += 1
        return count

    def generate_next_state(self, payload: dict) -> State:
        
        # Payload:
        # - state: State
        # - action: Action
        # - blocked: 1 | 0
        # - challenged: 1 | 0

        state = payload["state"] ## must be a copy of previous state
        action = payload["action"]
        parent_cards = action.parent_cards
        players = state.players
        players_dict = state.get_players_dict()
        acting_player_id = state.acting_player_id
        victim_id = state.victim_id
        
        if payload["blocked"] and payload["challenged"]:

            if state.phase == "RESOLVING":
                victim = players_dict[victim_id]
                attacker = players_dict[acting_player_id]
                blockables = victim.get_all_blockables()

                if action in blockables:
                    attacker.remove_card()
                    state.num_cards_per_player[acting_player_id] -= 1

                    old_card = list(parent_cards & victim.cards)[0]
                    victim.remove_card(old_card)
                    state.shuffle_card(old_card.name)

                    new_card = state.draw_card()
                    new_card = ALL_CARDS[new_card]
                    victim.add_card(new_card)

                    # new_state = State(players, state.turn_id + 1, state.deck, "AWAITING_ACTION", (acting_player_id + 1) % len(players), None, state.discard_pile)
                    state.turn_id += 1 
                    state.acting_player_id = (acting_player_id + 1) % len(players)

                    if self.num_active_players(state.num_cards_per_player) == 1:
                        state.phase = "GAME_OVER"
                    else:
                        state.phase = "AWAITING_ACTION"

                    return state
                
                elif action not in blockables:
                    card = victim.remove_card()
                    state.shuffle_card(card.name)
                    state.num_cards_per_player[victim_id] -= 1

                    self.resolve_actions(action, attacker, victim)

                    state.turn_id += 1 
                    state.acting_player_id = (acting_player_id + 1) % len(players)

                    if self.num_active_players(state.num_cards_per_player) == 1:
                        state.phase = "GAME_OVER"
                    else:
                        state.phase = "AWAITING_ACTION"

                    return state
                
            else:
                phase = "RESOLVING"
                return State(players, state.turn_id, state.deck, phase, acting_player_id, victim_id, state.discard_pile)
            
        elif payload["blocked"]:


        elif payload["challenged"]:

                


