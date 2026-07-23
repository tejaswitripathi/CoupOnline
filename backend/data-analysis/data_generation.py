import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "orchestration"))
sys.path.insert(0, str(ROOT / "database"))
sys.path.insert(0, str(ROOT / "coup-core"))

from database import SQLDatabase
from match_runner import (
    model_names_for_agents,
    parse_agent_list,
    player_agent_map,
    resolve_cli_agents,
    run_match,
)
from resolver import Resolver
from store import GAME_DB


N = 25
DEFAULT_SQLITE_PATH = ROOT / "database" / "coup_generated.sqlite3"
LOCAL_DATA_DIR = ROOT / "data-analysis" / "data"
TABLES = ("Game", "State", "Decision", "PlayerSnapshot", "Result")


def unique_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _card_name(card: Any) -> str:
    return card.name if hasattr(card, "name") else card


def _player_has_any_claim(state, player_id: int, card_names: set[str]) -> bool:
    player = state.get_players_dict().get(player_id)
    if player is None:
        return False
    return any(_card_name(card) in card_names for card in player.cards)


def claimed_card_for_decision(state, decision: dict) -> str | None:
    command = decision.get("command")

    if command == "declare":
        action = decision.get("action")
        claims = Resolver.ACTION_CLAIMS.get(action)
        return "/".join(sorted(claims)) if claims else None

    if command == "respond" and decision.get("response") == "block":
        pending_action = getattr(state, "pending_action", None)
        claims = Resolver.BLOCK_CLAIMS.get(pending_action)
        return "/".join(sorted(claims)) if claims else None

    return None


def is_bluff_for_decision(state, player_id: int, decision: dict) -> bool | None:
    command = decision.get("command")

    if command == "declare":
        action = decision.get("action")
        claims = Resolver.ACTION_CLAIMS.get(action)
        if claims:
            return not _player_has_any_claim(state, player_id, claims)

        forbidden_claims = Resolver.FORBIDDEN_ACTION_CLAIMS.get(action)
        if forbidden_claims:
            return _player_has_any_claim(state, player_id, forbidden_claims)

    if command == "respond" and decision.get("response") == "block":
        pending_action = getattr(state, "pending_action", None)
        claims = Resolver.BLOCK_CLAIMS.get(pending_action)
        if claims:
            return not _player_has_any_claim(state, player_id, claims)

    return None


def _legal_actions_from_observation(observation: dict) -> dict | None:
    private_view = observation.get("private_view") or {}
    return private_view.get("legal_next")


def persist_match(
    sql_db: SQLDatabase,
    game_id: str,
    match_result: dict,
    experiment_id: str | None = None,
) -> dict[str, int | str | None]:
    """Persist one completed in-memory match into the relational/Mongo tables."""
    record = GAME_DB.get_game(game_id)
    states = record.state_stack.get_states()
    state_ids = [unique_id("state") for _ in states]

    for state_seq, (state, state_id) in enumerate(zip(states, state_ids)):
        sql_db.insert_state(
            state,
            game_id=game_id,
            state_id=state_id,
            state_seq=state_seq,
            experiment_id=experiment_id,
        )

    decision_count = 0
    decision_state_index = 0
    for observation in match_result.get("observations", []):
        decision = observation.get("agent", {}).get("decision")
        player_id = observation.get("player_id")
        if not decision or player_id is None:
            continue

        state_index = min(decision_state_index, len(states) - 1)
        decision_state = states[state_index]
        agent = observation.get("agent", {})
        sql_db.insert_decision(
            game_id=game_id,
            state_id=state_ids[state_index],
            decision_id=unique_id("decision"),
            player_id=player_id,
            decision=decision,
            provider=agent.get("provider"),
            model=agent.get("model"),
            legal_actions=_legal_actions_from_observation(observation),
            claimed_card=claimed_card_for_decision(decision_state, decision),
            is_bluff=is_bluff_for_decision(decision_state, player_id, decision),
            resolved_successfully=not bool(observation.get("error")),
        )
        decision_count += 1

        if decision.get("command") != "noop" and decision_state_index + 1 < len(states):
            decision_state_index += 1

    game_summary = match_result.get("game", {})
    winner_id = game_summary.get("winner_id")
    player_labels = match_result.get("player_labels", {})
    sql_db.insert_result(
        game_id=game_id,
        winner_id=winner_id,
        winner_name=player_labels.get(winner_id) if winner_id is not None else None,
        total_turns=game_summary.get("turn_id"),
        total_states=len(states),
    )

    return {
        "game_id": game_id,
        "states": len(states),
        "decisions": decision_count,
        "winner_id": winner_id,
    }


def dump_tables_to_json(
    sql_db: SQLDatabase,
    data_dir: str | Path = LOCAL_DATA_DIR,
) -> dict[str, int]:
    """Write every table to `data_dir` as one JSON file per table.

    Used as a fallback when the MongoDB sync fails: the rows already live in the
    local SQLite database, so we read them back out and emit clean JSON with the
    JSON/boolean columns decoded from their stored representation.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, int] = {}
    for table in TABLES:
        rows = sql_db.table_rows(table)
        json_columns = sql_db.JSON_COLUMNS.get(table, set())
        bool_columns = sql_db.BOOL_COLUMNS.get(table, set())
        for row in rows:
            for column in json_columns:
                if isinstance(row.get(column), str):
                    row[column] = json.loads(row[column])
            for column in bool_columns:
                if row.get(column) is not None:
                    row[column] = bool(row[column])

        path = data_dir / f"{table.lower()}.json"
        path.write_text(json.dumps(rows, indent=2, default=str))
        written[table] = len(rows)

    return written


def generate_games(
    *,
    num_games: int = N,
    agents: str | None = None,
    include_random: bool = False,
    max_steps: int = 200,
    sqlite_path: str | Path = DEFAULT_SQLITE_PATH,
    sync_to_mongo: bool = True,
    require_mongo: bool = False,
    clear: bool = False,
    clear_mongo: bool = False,
    game_id_prefix: str = "generated",
    experiment_id: str | None = None,
    quiet: bool = False,
) -> list[dict[str, int | str | None]]:
    assert num_games >= 1, "num_games must be at least 1."

    experiment_id = experiment_id or unique_id("experiment")
    agent_names = resolve_cli_agents(parse_agent_list(agents), include_random)
    player_agents = player_agent_map(agent_names)
    player_model_names = model_names_for_agents(agent_names)
    summaries = []

    with SQLDatabase(
        sqlite_path=sqlite_path,
        sync_to_mongo=sync_to_mongo,
        require_mongo=require_mongo,
    ) as sql_db:
        if clear:
            sql_db.clear_all(include_mongo=clear_mongo)

        try:
            for game_number in range(1, num_games + 1):
                game_id = unique_id(game_id_prefix)
                match_result = run_match(
                    game_id=game_id,
                    num_players=len(agent_names),
                    player_agents=player_agents,
                    max_steps=max_steps,
                    include_private_view=True,
                )
                summary = persist_match(sql_db, game_id, match_result, experiment_id=experiment_id)
                summaries.append(summary)

                if not quiet:
                    print(
                        f"{game_number}/{num_games} saved {summary['game_id']}: "
                        f"{summary['states']} states, {summary['decisions']} decisions, "
                        f"winner={summary['winner_id']}; players={', '.join(player_model_names)}",
                        flush=True,
                    )
        except Exception:
            # A require_mongo run raises on the first failed Mongo write; persist
            # what SQLite already holds to local JSON before propagating.
            if sql_db.last_mongo_error is not None:
                _save_local_fallback(sql_db)
            raise

        if sql_db.last_mongo_error is not None:
            print(f"Warning: MongoDB sync failed: {sql_db.last_mongo_error}", file=sys.stderr)
            _save_local_fallback(sql_db)

    return summaries


def _save_local_fallback(sql_db: SQLDatabase) -> None:
    written = dump_tables_to_json(sql_db)
    counts = ", ".join(f"{table}={count}" for table, count in written.items())
    print(f"Saved local JSON fallback to {LOCAL_DATA_DIR} ({counts})", file=sys.stderr)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Coup match data into SQL tables mirrored to MongoDB.")
    parser.add_argument("--num-games", type=int, default=N)
    parser.add_argument(
        "--agents",
        default=None,
        help="Comma-separated or bracketed agent list, e.g. --agents=random,random or --agents=[gpt,claude,gemini]",
    )
    parser.add_argument("--include-random", action="store_true")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--sqlite-path", default=str(DEFAULT_SQLITE_PATH))
    parser.add_argument("--no-mongo", action="store_true", help="Only write the local SQLite database.")
    parser.add_argument("--require-mongo", action="store_true", help="Fail if MongoDB mirroring fails.")
    parser.add_argument("--clear", action="store_true", help="Clear existing local rows before generating.")
    parser.add_argument("--clear-mongo", action="store_true", help="Also clear mirrored Mongo collections with --clear.")
    parser.add_argument("--game-id-prefix", default="generated")
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    generate_games(
        num_games=args.num_games,
        agents=args.agents,
        include_random=args.include_random,
        max_steps=args.max_steps,
        sqlite_path=args.sqlite_path,
        sync_to_mongo=not args.no_mongo,
        require_mongo=args.require_mongo,
        clear=args.clear,
        clear_mongo=args.clear_mongo,
        game_id_prefix=args.game_id_prefix,
        experiment_id=args.experiment_id,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
