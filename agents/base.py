import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


SYSTEM_PROMPT = """You are playing Coup.
You only know the private view supplied for your player. Do not assume hidden
cards for other players. Choose exactly one legal next command from legal_next.

Return only JSON in one of these shapes:
{"command":"declare","action":"Income"}
{"command":"declare","action":"Steal","target_player_id":2}
{"command":"respond","response":"pass"}
{"command":"respond","response":"challenge"}
{"command":"respond","response":"block"}
{"command":"select_card","card":"Duke"}
{"command":"select_card","keep_cards":["Ambassador","Captain"]}
{"command":"noop"}

Prefer actions that improve your chance to win, but stay valid for the current
phase and player.
"""


DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "command": {
            "type": "string",
            "enum": ["declare", "respond", "select_card", "noop"],
        },
        "action": {
            "type": "string",
            "enum": [
                "Income",
                "Foreign Aid",
                "Coup",
                "Tax",
                "Steal",
                "Assassinate",
                "Exchange",
            ],
        },
        "target_player_id": {"type": ["integer", "null"]},
        "response": {
            "type": "string",
            "enum": ["pass", "challenge", "block"],
        },
        "card": {"type": "string"},
        "keep_cards": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["command"],
}


class AgentAPIError(RuntimeError):
    pass


def _env_paths() -> list[Path]:
    roots = [Path.cwd(), Path(__file__).resolve().parent]
    paths = []
    for root in roots:
        for candidate_root in (root, *root.parents):
            env_path = candidate_root / ".env"
            if env_path not in paths:
                paths.append(env_path)
    return paths


def _parse_env_file(env_path: Path) -> dict[str, str]:
    values = {}
    if not env_path.exists():
        return values

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if "#" in value and not value.startswith(("'", '"')):
            value = value.split("#", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value

    return values


def get_env_value(key: str) -> str | None:
    value = os.environ.get(key)
    if value:
        return value

    for env_path in _env_paths():
        value = _parse_env_file(env_path).get(key)
        if value:
            return value
    return None


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AgentAPIError(f"LLM API returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise AgentAPIError(f"Could not reach LLM API: {exc.reason}") from exc


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_decision(decision: dict, private_view: dict) -> dict:
    command = decision.get("command")
    legal_next = private_view.get("legal_next", {})

    if command == "declare":
        legal_actions = legal_next.get("declarations", [])
        action = decision.get("action")
        selected = next((item for item in legal_actions if item["action"] == action), None)
        if not selected:
            raise AgentAPIError(f"Agent declared illegal action: {action}")
        normalized = {"command": "declare", "action": action}
        if selected.get("requires_target"):
            target_id = decision.get("target_player_id")
            if target_id not in selected.get("valid_target_ids", []):
                raise AgentAPIError(f"Agent selected illegal target: {target_id}")
            normalized["target_player_id"] = target_id
        return normalized

    if command == "respond":
        response = decision.get("response")
        if response not in legal_next.get("responses", []):
            raise AgentAPIError(f"Agent selected illegal response: {response}")
        return {"command": "respond", "response": response}

    if command == "select_card":
        selection = legal_next.get("selection")
        if not selection:
            raise AgentAPIError("Agent selected a card when no selection is pending.")

        if selection["kind"] == "lose_influence":
            card = decision.get("card")
            if card not in selection.get("cards", []):
                raise AgentAPIError(f"Agent selected illegal card: {card}")
            return {"command": "select_card", "card": card}

        if selection["kind"] == "exchange":
            keep_cards = list(decision.get("keep_cards") or [])
            candidates = list(selection.get("candidates") or [])
            if len(keep_cards) != selection.get("keep_count"):
                raise AgentAPIError("Agent selected the wrong number of exchange cards.")
            for card in keep_cards:
                if card not in candidates:
                    raise AgentAPIError(f"Agent selected unavailable exchange card: {card}")
                candidates.remove(card)
            return {"command": "select_card", "keep_cards": keep_cards}

    if command == "noop":
        if any(legal_next.get(key) for key in ("declarations", "responses")) or legal_next.get("selection"):
            raise AgentAPIError("Agent returned noop despite having a legal move.")
        return {"command": "noop"}

    raise AgentAPIError(f"Unknown agent command: {command}")


class CoupLLMAgent:
    provider = None
    model = None

    def build_user_prompt(self, private_view: dict) -> str:
        return json.dumps(
            {
                "task": "Choose the next Coup command for this player.",
                "private_view": private_view,
            },
            sort_keys=True,
        )

    def decide(self, private_view: dict) -> dict:
        raw_output = self._call_model(private_view)
        decision = normalize_decision(_extract_json_object(raw_output), private_view)
        return {
            "provider": self.provider,
            "model": self.model,
            "decision": decision,
            "raw_output": raw_output,
        }

    def _call_model(self, private_view: dict) -> str:
        raise NotImplementedError
