import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coup-api"))
sys.path.insert(0, str(ROOT / "agents"))

from base import AgentAPIError
from store import GAME_DB


DEFAULT_AGENTS = ["gpt", "gemini", "claude"]
AGENT_POOL = ["gpt", "gemini", "claude", "random"]


class RandomAgent:
    provider = "local"
    model = "random"

    def decide(self, private_view: dict) -> dict:
        legal_next = private_view["legal_next"]
        declarations = legal_next.get("declarations") or []
        responses = legal_next.get("responses") or []
        selection = legal_next.get("selection")

        if declarations:
            action = self._choose_declaration(declarations)
            decision = {"command": "declare", "action": action["action"]}
            if action.get("requires_target"):
                decision["target_player_id"] = random.choice(action["valid_target_ids"])
            return self._result(decision)

        if responses:
            response = "pass"
            if "block" in responses and random.random() < 0.25:
                response = "block"
            elif "challenge" in responses and random.random() < 0.15:
                response = "challenge"
            return self._result({"command": "respond", "response": response})

        if selection:
            if selection["kind"] == "lose_influence":
                return self._result({"command": "select_card", "card": selection["cards"][0]})
            if selection["kind"] == "exchange":
                return self._result({
                    "command": "select_card",
                    "keep_cards": selection["candidates"][:selection["keep_count"]],
                })

        return self._result({"command": "noop"})

    def _choose_declaration(self, declarations: list[dict]) -> dict:
        by_name = {item["action"]: item for item in declarations}
        for action in ("Coup", "Assassinate", "Tax", "Steal", "Exchange", "Foreign Aid", "Income"):
            if action in by_name:
                return by_name[action]
        return declarations[0]

    def _result(self, decision: dict) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "decision": decision,
            "raw_output": decision,
        }


def _agent_classes():
    from claude_agent import ClaudeAgent
    from gemini_agent import GeminiAgent
    from gpt_agent import GPTAgent

    return {
        "gpt": GPTAgent,
        "openai": GPTAgent,
        "gemini": GeminiAgent,
        "claude": ClaudeAgent,
        "anthropic": ClaudeAgent,
        "random": RandomAgent,
    }


def _make_agent(agent_name: str):
    agent_cls = _agent_classes().get(agent_name)
    if not agent_cls:
        raise AssertionError(f"Unknown agent: {agent_name}")
    try:
        return agent_cls()
    except AgentAPIError as exc:
        raise AssertionError(str(exc)) from exc


def _next_player_id(state) -> int | None:
    if state.phase == "AWAITING_ACTION":
        return state.acting_player_id
    if state.phase in ("AWAITING_CHALLENGE", "AWAITING_BLOCK_OR_CHALLENGE"):
        pending = sorted(list(getattr(state, "pending_responses", set())))
        return pending[0] if pending else None
    if state.phase == "AWAITING_BLOCK_CHALLENGE":
        return state.acting_player_id
    if state.phase == "AWAITING_CARD_SELECTION":
        selections = getattr(state, "pending_selections", [])
        return selections[0]["player_id"] if selections else None
    return None


def _state_observation(game_id: str) -> dict:
    summary = GAME_DB.game_summary(game_id)
    state = GAME_DB.latest_state(game_id)

    def card_name(card) -> str:
        return card.name if hasattr(card, "name") else card

    summary["players"] = [
        {
            "id": player.id,
            "num_coins": player.num_coins,
            "num_cards": len(player.cards),
            "cards": [card_name(card) for card in player.cards],
            "is_active": len(player.cards) > 0,
        }
        for player in state.players
    ]
    summary["pending_action"] = getattr(state, "pending_action", None)
    summary["victim_id"] = getattr(state, "victim_id", None)
    summary["challenger_id"] = getattr(state, "challenger_id", None)
    summary["blocker_id"] = getattr(state, "blocker_id", None)
    pending_selections = getattr(state, "pending_selections", [])
    summary["pending_selection"] = pending_selections[0] if pending_selections else None
    return summary


def run_match(
    game_id: str | None = None,
    num_players: int | None = None,
    player_agents: dict[int, str] | None = None,
    max_steps: int = 200,
    include_private_view: bool = False,
    on_observation=None,
) -> dict:
    player_agents = {
        int(player_id): agent_name
        for player_id, agent_name in (player_agents or {}).items()
    }
    if not player_agents:
        player_agents = {player_id: agent for player_id, agent in enumerate(DEFAULT_AGENTS, start=1)}

    if num_players is None:
        num_players = len(player_agents)

    record = GAME_DB.create_game(
        game_id=game_id,
        num_players=num_players,
        player_agents=player_agents,
    )
    game_id = record.id
    agents = {
        player_id: _make_agent(player_agents.get(player_id, "random"))
        for player_id in range(1, num_players + 1)
    }
    player_labels = {
        player_id: getattr(agent, "model", getattr(agent, "provider", f"player_{player_id}"))
        for player_id, agent in agents.items()
    }

    observations = []

    for step in range(max_steps):
        state = GAME_DB.latest_state(game_id)
        if state.phase == "GAME_OVER":
            break

        player_id = _next_player_id(state)
        if player_id is None:
            observations.append({
                "step": step,
                "error": f"No eligible player for phase {state.phase}",
                "state": _state_observation(game_id),
            })
            break

        private_view = GAME_DB.private_view(game_id, player_id)
        agent = agents[player_id]
        try:
            decision_result = agent.decide(private_view)
            next_state = GAME_DB.dispatch_decision(game_id, player_id, decision_result["decision"])
        except Exception as exc:
            observation = {
                "step": step,
                "player_id": player_id,
                "player_labels": player_labels,
                "agent": {
                    "provider": getattr(agent, "provider", "unknown"),
                    "model": getattr(agent, "model", "unknown"),
                    "decision": None,
                },
                "error": f"{type(exc).__name__}: {exc}",
                "state": _state_observation(game_id),
            }
            observations.append(observation)
            if on_observation:
                on_observation(observation)
            break

        observation = {
            "step": step,
            "player_id": player_id,
            "player_labels": player_labels,
            "agent": {
                    "provider": decision_result["provider"],
                    "model": decision_result["model"],
                    "decision": decision_result["decision"],
                    "thoughts": decision_result.get("thoughts"),
                    "fallback": decision_result.get("fallback", False),
                },
                "state": _state_observation(game_id),
            }
        if include_private_view:
            observation["private_view"] = private_view
        observations.append(observation)
        if on_observation:
            on_observation(observation)

        if next_state.phase == "GAME_OVER":
            break

    return {
        "game": GAME_DB.game_summary(game_id),
        "observations": observations,
        "final_state": _state_observation(game_id),
        "player_labels": player_labels,
    }


def parse_agent_list(value: str | None) -> list[str]:
    if not value:
        return []

    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]

    return [
        item.strip().strip("'\"").lower()
        for item in value.split(",")
        if item.strip()
    ]


def resolve_cli_agents(agent_names: list[str], include_random: bool = False) -> list[str]:
    available_agents = set(_agent_classes())

    if not agent_names:
        agent_names = list(DEFAULT_AGENTS)

    unknown_agents = [agent for agent in agent_names if agent not in available_agents]
    if unknown_agents:
        raise AssertionError(f"Unknown agent(s): {', '.join(unknown_agents)}")

    if len(agent_names) == 1:
        candidates = [agent for agent in DEFAULT_AGENTS if agent != agent_names[0]]
        if not candidates:
            candidates = [agent for agent in AGENT_POOL if agent != agent_names[0]]
        agent_names = agent_names + [random.choice(candidates)]

    if include_random and "random" not in agent_names:
        assert len(agent_names) < 4, "--include-random requires room for a player; max players is 4."
        agent_names = agent_names + ["random"]

    assert 2 <= len(agent_names) <= 4, "Coup supports 2 to 4 players in this implementation."
    return agent_names


def player_agent_map(agent_names: list[str]) -> dict[int, str]:
    return {index: agent_name for index, agent_name in enumerate(agent_names, start=1)}


def model_name_for_agent(agent_name: str) -> str:
    agent_cls = _agent_classes()[agent_name]
    return getattr(agent_cls, "model", agent_name)


def model_names_for_agents(agent_names: list[str]) -> list[str]:
    return [model_name_for_agent(agent_name) for agent_name in agent_names]


def _label(player_labels: dict[int, str], player_id: int | None) -> str:
    if player_id is None:
        return "unknown"
    return player_labels.get(player_id, f"player_{player_id}")


def _num_cards(state: dict, player_id: int | None) -> int | None:
    if player_id is None:
        return None
    for player in state.get("players", []):
        if player["id"] == player_id:
            return player["num_cards"]
    return None


def _player_summaries(state: dict, player_labels: dict[int, str]) -> list[str]:
    lines = []
    for player in state.get("players", []):
        cards = ", ".join(player.get("cards", []))
        lines.append(
            f"{_label(player_labels, player['id'])} has {player['num_coins']} coins "
            f"and cards: [{cards}]."
        )
    return lines


def _is_turn_start(observation: dict) -> bool:
    decision = observation.get("agent", {}).get("decision")
    return bool(decision and decision.get("command") == "declare")


def _is_turn_end(observation: dict) -> bool:
    return observation.get("state", {}).get("phase") in ("AWAITING_ACTION", "GAME_OVER")


def format_observation_lines(observation: dict) -> list[str]:
    state = observation["state"]
    decision = observation["agent"]["decision"]
    player_labels = observation.get("player_labels", {})
    agent = _label(player_labels, observation.get("player_id"))
    thoughts = observation.get("agent", {}).get("thoughts")

    if observation.get("error"):
        return [f"{agent} could not choose a move: {observation['error']}"]

    if not decision:
        return [f"{agent} did not choose a move."]

    lines = []
    if thoughts:
        lines.append(f"> {agent} thoughts: {thoughts}")

    command = decision["command"]
    if command == "declare":
        action = decision["action"]
        target_id = decision.get("target_player_id")
        if target_id is not None:
            lines.append(f"{agent} is choosing {action} against {_label(player_labels, target_id)}.")
            return lines
        lines.append(f"{agent} is choosing {action}.")
        return lines

    if command == "respond":
        response = decision["response"]
        if response == "block":
            lines.append(f"{agent} blocks.")
            return lines
        if response == "pass":
            lines.append(f"{agent} passes.")
            return lines
        if response == "challenge":
            lines.append(f"{agent} challenges.")
            pending_selection = state.get("pending_selection")
            loser_id = pending_selection.get("player_id") if pending_selection else None
            if loser_id is not None:
                if loser_id == observation.get("player_id"):
                    winner_id = state.get("blocker_id") or state.get("acting_player_id")
                else:
                    winner_id = observation.get("player_id")
                lines.append(
                    f"{_label(player_labels, winner_id)} has won the challenge. "
                    f"{_label(player_labels, loser_id)} must discard a card."
                )
            return lines

    if command == "select_card":
        if "card" in decision:
            lines.append(f"{agent} discards {decision['card']}.")
            if _num_cards(state, observation.get("player_id")) == 0:
                lines.append(f"{agent} has run out of cards!")
            return lines
        if "keep_cards" in decision:
            lines.append(f"{agent} keeps {', '.join(decision['keep_cards'])} after Exchange.")
            return lines

    if command == "noop":
        lines.append(f"{agent} waits.")
        return lines

    lines.append(f"{agent} chooses {decision}.")
    return lines


def format_observation(observation: dict) -> str:
    return "\n".join(format_observation_lines(observation))


class MatchPrinter:
    def __init__(self):
        self.started = False

    def print_observation(self, observation: dict) -> None:
        if _is_turn_start(observation):
            if self.started:
                print("", flush=True)
            self.started = True
            print(f"{_label(observation['player_labels'], observation['player_id'])}'s turn.", flush=True)

        print(format_observation(observation), flush=True)

        if _is_turn_end(observation) and not observation.get("error"):
            for line in _player_summaries(observation["state"], observation["player_labels"]):
                print(line, flush=True)


def print_match(result: dict) -> None:
    printer = MatchPrinter()
    for observation in result["observations"]:
        printer.print_observation(observation)
    game = result["game"]
    winner = _label(result["player_labels"], game["winner_id"])
    print(f"{winner} wins!" if game["winner_id"] is not None else "Game ended without a winner.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run observed Coup matches between agents.")
    parser.add_argument("--num-games", type=int, default=1, help="Number of games to run successively.")
    parser.add_argument(
        "--agents",
        default=None,
        help="Comma-separated or bracketed agent list, e.g. --agents=[gpt,claude,gemini]",
    )
    parser.add_argument(
        "--include-random",
        action="store_true",
        help="Force a random player into the game if one is not already present.",
    )
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--include-private-view", action="store_true")
    parser.add_argument("--game-id-prefix", default="match")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    assert args.num_games >= 1, "--num-games must be at least 1."

    agent_names = resolve_cli_agents(parse_agent_list(args.agents), args.include_random)
    player_agents = player_agent_map(agent_names)
    player_model_names = model_names_for_agents(agent_names)

    for game_number in range(1, args.num_games + 1):
        if game_number > 1:
            print(f"\n---GAME {game_number}---\n")

        print(f"players: {', '.join(player_model_names)}", flush=True)
        printer = MatchPrinter()
        result = run_match(
            game_id=f"{args.game_id_prefix}-{game_number}",
            num_players=len(agent_names),
            player_agents=player_agents,
            max_steps=args.max_steps,
            include_private_view=args.include_private_view,
            on_observation=printer.print_observation,
        )
        game = result["game"]
        winner = _label(result["player_labels"], game["winner_id"])
        print(f"{winner} wins!" if game["winner_id"] is not None else "Game ended without a winner.", flush=True)


if __name__ == "__main__":
    main()
