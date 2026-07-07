import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coup-core"))

from state import State
from player import Player
from state_stack import StateStack
from resolver import Resolver

# Mock Database
players = [Player(1), Player(2), Player(3), Player(4)]
state = State(players, turn_id=0, deck=None, phase=None)
STATE_STACK = StateStack(states=[state])
RESOLVER = Resolver()
