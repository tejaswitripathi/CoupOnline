import sqlite3
from pathlib import Path

import pandas as pd

import scipy.stats as stats
from scipy.stats import binomtest

# Resolve the DB path relative to this file so it works no matter where you run from.
DB_PATH = Path(__file__).resolve().parent.parent / "database" / "coup_generated.sqlite3"
MODELS = ["gemini-3.1-flash-lite", "gpt-5.4-nano", "claude-haiku-4-5"]

# 1. Open a connection (sqlite3 is built in, no SQLAlchemy needed for reads).
conn = sqlite3.connect(DB_PATH)

# 2. Extract the tables into DataFrames.
states = pd.read_sql_query("SELECT * FROM State", conn)
playersnapshots = pd.read_sql_query("SELECT * FROM PlayerSnapshot", conn)
games = pd.read_sql_query("SELECT * FROM Game", conn)
decisions = pd.read_sql_query("SELECT * FROM Decision", conn)
results = pd.read_sql_query("SELECT * FROM Result", conn)

conn.close()

# 3. Sanity check.
print(f"games: {len(games)} rows")
print(games.columns.tolist())
print(f"states: {len(states)} rows")
print(states.columns.tolist())
print(f"decisions: {len(decisions)} rows")
print(decisions.columns.tolist())
print(f"results: {len(results)} rows")
print(results.columns.tolist())
print(f"playersnapshots: {len(playersnapshots)} rows")
print(playersnapshots.columns.tolist())
print()

observed = results.groupby("winner_name").size()
# print(observed)
print("--WINRATES--")
winrates = observed / observed.sum()
winrates = winrates.sort_values(ascending=False)
print(winrates)
print()

print("Chi2 test:")
chi2_stat, p_value = stats.chisquare(f_obs=observed)
print(f"Chi2 stat: {chi2_stat}")
print(f"P-value: {p_value}")
print()

print("Binomial test:")
binom_test = binomtest(observed.sort_values(ascending=False).iloc[0], n=observed.sum(), p=1/3)
print(f"P-value: {binom_test.pvalue}")
print()

print("--CARD CONFIGURATIONS--")
# print()

starting_hands = {m: [] for m in MODELS}

# player_name in PlayerSnapshot is only "Player 1/2/3", and player_id (1/2/3)
# is reused across games, so the model for a seat is game-specific. Build a
# (game_id, player_id) -> model mapping from the Decision table.
player_models = decisions.groupby(["game_id", "player_id"])["model"].first()

# The starting state of each game is the one with the lowest state_seq.
first_states = (
    states.sort_values("state_seq")
    .groupby("game_id")
    .first()
    .reset_index()[["game_id", "state_id"]]
)

for game_id, state_id in first_states.itertuples(index=False):
    snap = playersnapshots[playersnapshots["state_id"] == state_id]
    for _, row in snap.iterrows():
        model = player_models.get((game_id, row["player_id"]))
        if model in starting_hands:
            starting_hands[model].append(row["cards"])

