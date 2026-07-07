import random
from player import Player

## Phases
AWAITING_ACTION = "AWAITING_ACTION"
AWAITING_CHALLENGE = "AWAITING_CHALLENGE"
AWAITING_BLOCK_OR_CHALLENGE = "AWAITING_BLOCK_OR_CHALLENGE"
AWAITING_BLOCK_CHALLENGE = "AWAITING_BLOCK_CHALLENGE"
AWAITING_CARD_SELECTION = "AWAITING_CARD_SELECTION"
RESOLVING = "RESOLVING"
GAME_OVER = "GAME_OVER"

class State():

    def __init__(self, 
                 players: list[Player],
                 turn_id: int, 
                 deck: list[str] | None, 
                 phase: str | None,
                 acting_player_id: int = None,
                 victim_id: int = None,
                 discard_pile: list[str] = []):

        num_players = len(players)
        
        assert 0 < num_players <= 4, "Invalid number of players!"

        self.players = players
        self.turn_id = turn_id
        self.deck = deck
        self.phase = phase
        
        if turn_id == 0:
            self.deck = self.build_deck()
            self.create_game()

        self.num_cards_per_player = {p.id: len(p.cards) for p in self.players}

    def build_deck(self) -> list[str]:
        deck = ["Duke", "Captain", "Assassin", "Contessa", "Ambassador"] * 3
        random.shuffle(deck)
        return deck

    def shuffle_card(self, card: str) -> None:
        self.deck.append(card)
        random.shuffle(self.deck)

    def draw_card(self) -> str:
        return self.deck.pop(0)
    
    def discard(self, card: str) -> None:
        self.discard_pile.append(card)
    
    def create_game(self) -> None:
        for player in self.players:
            player.cards = self.deck[:2]
            self.deck.pop(0)
            self.deck.pop(0)
        starting_index = random.sample(range(len(self.players)), 1)[0]
        self.acting_player_id = self.players[starting_index].id
        self.phase = "AWAITING_ACTION"

    def get_players_dict(self) -> dict:
        return {p.id: p for p in self.players}


# def initialize_next_turn(prev_state: State) -> State:
    
#     assert prev_state.phase == "RESOLVING", "Invalid state for next turn!"

#     next_state = State(players = prev_state.players, 
#                        turn_id = prev_state.turn_id + 1, 
#                        deck = prev_state.deck,
#                        phase = "AWAITING_ACTION",
#                        acting_player_id = (prev_state.acting_player_id + 1) % len(prev_state.players))
#     return next_state