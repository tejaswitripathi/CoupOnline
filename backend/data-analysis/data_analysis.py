import argparse
import random
import sys
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))

from database import SQLDatabase

try:
    import certifi
    from dotenv import load_dotenv
    from pymongo import MongoClient
except ImportError:  # Keep local SQLite usable without the Mongo extras installed.
    certifi = None
    load_dotenv = None
    MongoClient = None

"""WHAT THIS FILE DOES: 
    - from mongodb storage, fetch all data
    - perform data analysis, simple"""

client = MongoClient(os.environ.get("MONGODB_URI"))

# Select database and collection
db = client["my_database"]
collection = db["my_collection"]