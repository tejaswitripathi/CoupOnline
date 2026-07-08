import random

from card import Card, all_cards
from action import Action

class Player():

    def __init__(self, id: int):

        self.num_coins = 2
        self.id = id
        self.cards = []

    def remove_card(self, card: Card | None) -> Card:
        assert len(self.cards) > 0, "Player has no cards to remove."
        if not card:
            card = random.choice(self.cards)

        self.cards.remove(card)
        return card
    
    def add_card(self, card: Card) -> None:
        assert len(self.cards) < 2, "Player cannot have more than 2 cards."

        self.cards.append(card)

    def get_all_legal_actions(self) -> set[Action]:
        all_legal_actions = set()
        for c in self.cards:
            all_legal_actions.update(c.actions)
        return all_legal_actions
    
    def get_all_blockables(self) -> set[Action]:
        all_blockables = set()
        for c in self.cards:
            all_blockables.update(c.blockables)
        return all_blockables