import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "coup-core"))

from state import State

class SQLDatabase():

    def __init__(self):
        """TODO: Creates tables"""
        pass

    def insert_state(self, payload: State):
        """TODO: """
        pass