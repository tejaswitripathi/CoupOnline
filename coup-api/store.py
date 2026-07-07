from coup-core.state import State
from coup-core.player import Player
from coup-core.state_stack import StateStack

# Mock Database
players = [Player(1), Player(2), Player(3), Player(4)]
state = State(players, turn_id = 0)
STATE_STACK = StateStack(states = [state])

