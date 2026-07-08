import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "orchestration"))

from store import GAME_DB

N = 200     # number of games

# 1. Clear DB if it currently contains states



# 2. Populate DB with new states according to N