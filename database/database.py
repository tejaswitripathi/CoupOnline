import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "coup-core"))

from state import State

try:
    import certifi
    from dotenv import load_dotenv
    from pymongo import MongoClient
except ImportError:  # Keep local SQLite usable without the Mongo extras installed.
    certifi = None
    load_dotenv = None
    MongoClient = None


class SQLDatabase:
    """Relational Coup game storage, mirrored to MongoDB for shared access.

    SQLite owns the SQL schema and constraint checks locally. When `MONGODB_URI`
    is present, every inserted row is also upserted into the configured MongoDB
    database as one collection per table: game, state, decision, playersnapshot,
    and result.
    """

    JSON_COLUMNS = {
        "State": {"player_ids", "deck", "discard_pile"},
        "Decision": {"legal_actions", "raw_decision"},
        "PlayerSnapshot": {"cards"},
    }
    BOOL_COLUMNS = {
        "State": {"blocked", "challenged"},
        "Decision": {"is_bluff", "resolved_successfully"},
        "PlayerSnapshot": {"active"},
    }
    PRIMARY_KEYS = {
        "Game": ("game_id",),
        "State": ("state_id",),
        "Decision": ("decision_id",),
        "PlayerSnapshot": ("state_id", "player_id"),
        "Result": ("game_id",),
    }
    ACTION_CLAIMS = {
        "Tax": "Duke",
        "Steal": "Captain",
        "Assassinate": "Assassin",
        "Exchange": "Ambassador",
        "Foreign Aid": "Duke",
    }

    def __init__(
        self,
        sqlite_path: str | Path = ":memory:",
        game_id: int | str | None = None,
        *,
        sync_to_mongo: bool = True,
        mongo_uri: str | None = None,
        mongo_db: str | None = None,
        mongo_collection_prefix: str = "",
        require_mongo: bool = False,
        mongo_timeout_ms: int = 5000,
    ):
        """Create the SQL tables and optionally prepare MongoDB mirroring.

        Args:
            sqlite_path: Local SQLite database path. Defaults to in-memory.
            game_id: Default game id used by `insert_state` when no id is given.
            sync_to_mongo: Mirror rows to MongoDB when configuration is present.
            mongo_uri: Overrides MONGODB_URI from the environment.
            mongo_db: Overrides MONGODB_DB from the environment.
            mongo_collection_prefix: Optional prefix for Mongo collection names.
            require_mongo: Raise if MongoDB cannot be configured or written to.
            mongo_timeout_ms: Server selection timeout for Mongo writes.
        """
        if load_dotenv:
            load_dotenv(ROOT / ".env")

        self._last_bigint_id = 0
        self.sqlite_path = str(sqlite_path)
        self.conn = sqlite3.connect(self.sqlite_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

        self.game_id = game_id if game_id is not None else self._new_bigint_id()
        self.mongo_collection_prefix = mongo_collection_prefix
        self.require_mongo = require_mongo
        self.mongo_client = None
        self.mongo_db = None
        self._mongo_indexes_ready = False
        self.mongo_timeout_ms = mongo_timeout_ms
        self.last_mongo_error = None

        self.mongo_uri = mongo_uri or os.environ.get("MONGODB_URI")
        self.mongo_db_name = mongo_db or os.environ.get("MONGODB_DB", "coup_research")
        self.sync_to_mongo = bool(sync_to_mongo and self.mongo_uri)

        if sync_to_mongo and require_mongo and not self.mongo_uri:
            raise RuntimeError("MONGODB_URI is required when require_mongo=True.")
        if sync_to_mongo and require_mongo and MongoClient is None:
            raise RuntimeError("pymongo, certifi, and python-dotenv are required for MongoDB sync.")

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS Game (
                game_id BIGINT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS State (
                state_id BIGINT PRIMARY KEY,
                game_id BIGINT NOT NULL,
                experiment_id VARCHAR,
                state_seq INTEGER NOT NULL,
                turn_id INTEGER NOT NULL,
                phase VARCHAR,
                player_ids JSON NOT NULL,
                acting_player_id INTEGER,
                deck JSON,
                discard_pile JSON,
                victim_id INTEGER,
                blocked BOOLEAN,
                challenged BOOLEAN,
                blocker_id INTEGER,
                challenger_id INTEGER,
                FOREIGN KEY (game_id) REFERENCES Game(game_id)
            );

            CREATE TABLE IF NOT EXISTS Decision (
                decision_id BIGINT PRIMARY KEY,
                game_id BIGINT NOT NULL,
                state_id BIGINT NOT NULL,
                player_id INTEGER NOT NULL,
                provider VARCHAR,
                model VARCHAR,
                decision_type VARCHAR NOT NULL,
                action VARCHAR,
                claimed_card VARCHAR,
                is_bluff BOOLEAN,
                target_player_id INTEGER,
                resolved_successfully BOOLEAN,
                legal_actions JSON,
                raw_decision JSON,
                FOREIGN KEY (game_id) REFERENCES Game(game_id),
                FOREIGN KEY (state_id) REFERENCES State(state_id)
            );

            CREATE TABLE IF NOT EXISTS PlayerSnapshot (
                state_id BIGINT NOT NULL,
                player_id INTEGER NOT NULL,
                player_name VARCHAR,
                cards JSON NOT NULL,
                num_coins INTEGER NOT NULL,
                active BOOLEAN NOT NULL,
                PRIMARY KEY (state_id, player_id),
                FOREIGN KEY (state_id) REFERENCES State(state_id)
            );

            CREATE TABLE IF NOT EXISTS Result (
                game_id BIGINT PRIMARY KEY,
                winner_name VARCHAR,
                winner_id INTEGER,
                total_turns BIGINT,
                total_states BIGINT,
                FOREIGN KEY (game_id) REFERENCES Game(game_id)
            );

            """
        )
        self._ensure_column("State", "experiment_id", "VARCHAR")
        self._ensure_column("State", "state_seq", "INTEGER")
        self._ensure_column("Decision", "provider", "VARCHAR")
        self._ensure_column("Decision", "model", "VARCHAR")
        self.conn.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_State_game_id_state_seq ON State(game_id, state_seq);
            CREATE INDEX IF NOT EXISTS idx_State_experiment_id_phase ON State(experiment_id, phase);
            CREATE INDEX IF NOT EXISTS idx_State_state_id ON State(state_id);
            CREATE INDEX IF NOT EXISTS idx_Decision_game_id_state_id ON Decision(game_id, state_id);
            CREATE INDEX IF NOT EXISTS idx_Decision_provider_model ON Decision(provider, model);
            CREATE INDEX IF NOT EXISTS idx_PlayerSnapshot_state_id ON PlayerSnapshot(state_id);
            """
        )
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {
            row["name"]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_mongo(self):
        if not self.sync_to_mongo:
            return None
        if self.mongo_db is not None:
            return self.mongo_db
        if MongoClient is None:
            if self.require_mongo:
                raise RuntimeError("pymongo, certifi, and python-dotenv are required for MongoDB sync.")
            self.sync_to_mongo = False
            return None

        kwargs = {"serverSelectionTimeoutMS": self.mongo_timeout_ms}
        if certifi is not None:
            kwargs.update({"tls": True, "tlsCAFile": certifi.where()})
        self.mongo_client = MongoClient(self.mongo_uri, **kwargs)
        self.mongo_db = self.mongo_client[self.mongo_db_name]
        return self.mongo_db

    def _ensure_mongo_indexes(self) -> None:
        db = self._ensure_mongo()
        if db is None or self._mongo_indexes_ready:
            return

        index_specs = {
            "Game": [
                ("idx_game_id_unique", [("game_id", 1)], {"unique": True}),
            ],
            "State": [
                ("idx_game_state_seq_unique", [("game_id", 1), ("state_seq", 1)], {"unique": True}),
                ("idx_experiment_phase", [("experiment_id", 1), ("phase", 1)], {}),
            ],
            "Decision": [
                ("idx_game_state", [("game_id", 1), ("state_id", 1)], {}),
                ("idx_provider_model", [("provider", 1), ("model", 1)], {}),
            ],
            "PlayerSnapshot": [
                ("idx_state_player_unique", [("state_id", 1), ("player_id", 1)], {"unique": True}),
            ],
            "Result": [
                ("idx_result_game_id_unique", [("game_id", 1)], {"unique": True}),
            ],
        }
        for table, specs in index_specs.items():
            collection = db[self._mongo_collection_name(table)]
            for name, keys, options in specs:
                collection.create_index(keys, name=name, **options)
        self._mongo_indexes_ready = True

    def _mongo_collection_name(self, table: str) -> str:
        return f"{self.mongo_collection_prefix}{table.lower()}"

    def _sync_row_to_mongo(self, table: str, row: dict[str, Any]) -> None:
        db = self._ensure_mongo()
        if db is None:
            return

        self._ensure_mongo_indexes()
        document = self._mongo_document(table, row)
        db[self._mongo_collection_name(table)].replace_one(
            {"_id": document["_id"]},
            document,
            upsert=True,
        )

    def _mongo_document(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        document = dict(row)
        for column in self.JSON_COLUMNS.get(table, set()):
            if isinstance(document.get(column), str):
                document[column] = json.loads(document[column])
        for column in self.BOOL_COLUMNS.get(table, set()):
            if document.get(column) is not None:
                document[column] = bool(document[column])

        pk = self.PRIMARY_KEYS[table]
        if len(pk) == 1:
            document["_id"] = document[pk[0]]
        else:
            document["_id"] = ":".join(str(document[key]) for key in pk)
        return document

    def _insert_row(self, table: str, row: dict[str, Any]) -> None:
        columns = list(row.keys())
        placeholders = ", ".join(["?"] * len(columns))
        column_sql = ", ".join(columns)
        update_columns = [column for column in columns if column not in self.PRIMARY_KEYS[table]]
        conflict_target = ", ".join(self.PRIMARY_KEYS[table])

        if update_columns:
            update_sql = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
            sql = (
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT({conflict_target}) DO UPDATE SET {update_sql}"
            )
        else:
            sql = (
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT({conflict_target}) DO NOTHING"
            )

        self.conn.execute(sql, [row[column] for column in columns])
        self.conn.commit()
        try:
            self._sync_row_to_mongo(table, row)
            self.last_mongo_error = None
        except Exception as exc:
            self.last_mongo_error = exc
            if self.require_mongo:
                raise

    def insert_game(self, game_id: int | str | None = None) -> int | str:
        game_id = self.game_id if game_id is None else game_id
        self._insert_row("Game", {"game_id": game_id})
        return game_id

    def insert_state(
        self,
        payload: State,
        game_id: int | str | None = None,
        state_id: int | str | None = None,
        state_seq: int | None = None,
        experiment_id: str | None = None,
    ) -> int | str:
        """Insert one Coup state and all player snapshots.

        Returns the `state_id` assigned to the state. If the state is terminal,
        a Result row is also upserted for the game.
        """
        game_id = game_id if game_id is not None else getattr(payload, "game_id", self.game_id)
        state_id = state_id if state_id is not None else getattr(payload, "state_id", None)
        state_id = state_id if state_id is not None else self._new_bigint_id()
        state_seq = state_seq if state_seq is not None else getattr(payload, "state_seq", None)
        state_seq = state_seq if state_seq is not None else self._count_states(game_id)
        experiment_id = experiment_id if experiment_id is not None else getattr(payload, "experiment_id", None)

        self.insert_game(game_id)
        players = list(getattr(payload, "players", []))
        player_ids = [player.id for player in players]

        self._insert_row(
            "State",
            {
                "state_id": state_id,
                "game_id": game_id,
                "experiment_id": experiment_id,
                "state_seq": state_seq,
                "turn_id": payload.turn_id,
                "phase": payload.phase,
                "player_ids": self._json(player_ids),
                "acting_player_id": getattr(payload, "acting_player_id", None),
                "deck": self._json(getattr(payload, "deck", [])),
                "discard_pile": self._json(getattr(payload, "discard_pile", [])),
                "victim_id": getattr(payload, "victim_id", None),
                "blocked": self._bool_or_none(getattr(payload, "blocked", None)),
                "challenged": self._bool_or_none(getattr(payload, "challenged", None)),
                "blocker_id": getattr(payload, "blocker_id", None),
                "challenger_id": getattr(payload, "challenger_id", None),
            },
        )

        for player in players:
            self._insert_player_snapshot(state_id, player)

        if payload.phase == "GAME_OVER":
            self.insert_result(game_id=game_id, state=payload)

        return state_id

    def _insert_player_snapshot(self, state_id: int, player: Any) -> None:
        self._insert_row(
            "PlayerSnapshot",
            {
                "state_id": state_id,
                "player_id": player.id,
                "player_name": getattr(player, "name", f"Player {player.id}"),
                "cards": self._json([self._card_name(card) for card in getattr(player, "cards", [])]),
                "num_coins": getattr(player, "num_coins", 0),
                "active": int(len(getattr(player, "cards", [])) > 0),
            },
        )

    def insert_decision(
        self,
        *,
        game_id: int | str | None = None,
        state_id: int | str,
        player_id: int,
        decision: dict[str, Any],
        legal_actions: Any = None,
        decision_id: int | str | None = None,
        provider: str | None = None,
        model: str | None = None,
        claimed_card: str | None = None,
        is_bluff: bool | None = None,
        resolved_successfully: bool | None = None,
    ) -> int | str:
        """Insert one agent/user decision row."""
        game_id = self.game_id if game_id is None else game_id
        decision_id = decision_id if decision_id is not None else self._new_bigint_id()
        decision_type, action, target_player_id = self._normalize_decision(decision)
        claimed_card = claimed_card if claimed_card is not None else self.ACTION_CLAIMS.get(action)

        self.insert_game(game_id)
        self._insert_row(
            "Decision",
            {
                "decision_id": decision_id,
                "game_id": game_id,
                "state_id": state_id,
                "player_id": player_id,
                "provider": provider,
                "model": model,
                "decision_type": decision_type,
                "action": action,
                "claimed_card": claimed_card,
                "is_bluff": self._bool_or_none(is_bluff),
                "target_player_id": target_player_id,
                "resolved_successfully": self._bool_or_none(resolved_successfully),
                "legal_actions": self._json(legal_actions),
                "raw_decision": self._json(decision),
            },
        )
        return decision_id

    def insert_result(
        self,
        *,
        game_id: int | str | None = None,
        state: State | None = None,
        winner_id: int | None = None,
        winner_name: str | None = None,
        total_turns: int | None = None,
        total_states: int | None = None,
    ) -> None:
        game_id = self.game_id if game_id is None else game_id

        if state is not None:
            live_players = [player for player in state.players if len(player.cards) > 0]
            if winner_id is None and len(live_players) == 1:
                winner_id = live_players[0].id
            if winner_name is None and len(live_players) == 1:
                winner_name = getattr(live_players[0], "name", f"Player {live_players[0].id}")
            if total_turns is None:
                total_turns = state.turn_id

        if total_states is None:
            total_states = self._count_states(game_id)

        self.insert_game(game_id)
        self._insert_row(
            "Result",
            {
                "game_id": game_id,
                "winner_name": winner_name,
                "winner_id": winner_id,
                "total_turns": total_turns,
                "total_states": total_states,
            },
        )

    def table_rows(self, table: str) -> list[dict[str, Any]]:
        cursor = self.conn.execute(f"SELECT * FROM {table}")
        return [dict(row) for row in cursor.fetchall()]

    def next_state(self, game_id: int | str, state_seq: int) -> dict[str, Any] | None:
        cursor = self.conn.execute(
            "SELECT * FROM State WHERE game_id = ? AND state_seq = ?",
            (game_id, state_seq + 1),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def clear_all(self, *, include_mongo: bool = False) -> None:
        for table in ("Result", "PlayerSnapshot", "Decision", "State", "Game"):
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()

        if include_mongo:
            db = self._ensure_mongo()
            if db is not None:
                for table in ("Result", "PlayerSnapshot", "Decision", "State", "Game"):
                    db[self._mongo_collection_name(table)].delete_many({})

    def close(self) -> None:
        self.conn.close()
        if self.mongo_client is not None:
            self.mongo_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def _count_states(self, game_id: int | str) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) AS count FROM State WHERE game_id = ?", (game_id,))
        return int(cursor.fetchone()["count"])

    def _normalize_decision(self, decision: dict[str, Any]) -> tuple[str, str | None, int | None]:
        command = decision.get("command")
        if command == "declare":
            return "declare", decision.get("action"), decision.get("target_player_id")
        if command == "respond":
            return "response", decision.get("response"), None
        if command == "select_card":
            action = "Exchange" if "keep_cards" in decision else "card_selection"
            return "select_card", action, None
        if command == "noop":
            return "noop", None, None
        raise ValueError(f"Unknown decision command: {command}")

    def _json(self, value: Any) -> str:
        return json.dumps(value, default=self._json_default)

    def _json_default(self, value: Any):
        if isinstance(value, set):
            return sorted(value)
        if hasattr(value, "name"):
            return value.name
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return str(value)

    def _card_name(self, card: Any) -> str:
        return card.name if hasattr(card, "name") else card

    def _bool_or_none(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(bool(value))

    def _new_bigint_id(self) -> int:
        # Microseconds since epoch plus a tiny random suffix fits in signed int64.
        candidate = (time.time_ns() // 1_000) * 1_000 + random.randint(0, 999)
        if candidate <= self._last_bigint_id:
            candidate = self._last_bigint_id + 1
        self._last_bigint_id = candidate
        return candidate
