

class Action():

    def __init__(self, 
                 name: str, 
                 cost: int, 
                 has_victim: bool, 
                 blockable: bool,
                 parent_cards: set[str] | None):
        
        self.name = name
        self.cost = cost
        self.has_victim = has_victim
        self.blockable = blockable
        self.parent_cards = parent_cards

def all_actions() -> dict[str]:
    actions = {}

    income = Action("Income", -1, False, False, None)
    actions["Income"] = income

    foreign_aid = Action("Foreign Aid", -2, False, True, {"Captain, Assassin, Contessa, Ambassador"})
    actions["Foreign Aid"] = foreign_aid

    coup = Action("Coup", 7, True, False, None)
    actions["Coup"] = coup

    tax = Action("Tax", -3, False, False, {"Duke"})
    actions["Tax"] = tax

    steal = Action("Steal", -2, True, True, {"Captain"})
    actions["Steal"] = steal

    assassinate = Action("Assassinate", 3, True, True, {"Assassin"})
    actions["Assassinate"] = assassinate

    exchange = Action("Exchange", 0, True, False, {"Ambassador"})
    actions["Exchange"] = exchange

    return actions

ALL_ACTIONS = all_actions()