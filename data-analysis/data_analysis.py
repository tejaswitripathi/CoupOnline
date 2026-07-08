import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))

from store import GAME_DB

