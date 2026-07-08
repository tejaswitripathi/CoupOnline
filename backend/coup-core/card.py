from action import Action, ALL_ACTIONS

class Card():

    def __init__(self, 
                 name: str, 
                 actions: set[Action] | None, 
                 blockables: set[Action] | None):
        
        self.name = name
        self.actions = actions
        self.blockables = blockables

def all_cards() -> dict[str]:
    cards = {}
    actions = ALL_ACTIONS

    duke = Card("Duke", {actions["Tax"]}, {actions["Foreign Aid"]})
    cards["Duke"] = duke

    captain = Card("Captain", {actions["Steal"]}, {actions["Steal"]})
    cards["Captain"] = captain

    assassin = Card("Assassin", {actions["Assassinate"]}, None)
    cards["Assassin"] = assassin

    contessa = Card("Contessa", None, {actions["Assassinate"]})
    cards["Contessa"] = contessa

    ambassador = Card("Ambassador", {actions["Exchange"]}, {actions["Steal"]})
    cards["Ambassador"] = ambassador

    return cards

ALL_CARDS = all_cards()