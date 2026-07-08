import json
import os
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.request


SYSTEM_PROMPT = """You are playing Coup.
You only know the private view supplied for your player. Do not assume hidden
cards for other players. Choose exactly one legal next command from legal_next.

Return only JSON in one of these shapes. You may include a "thoughts" field with
one concise sentence of public strategic rationale:
{"command":"declare","action":"Income","thoughts":"I need safe coins before taking a risk."}
{"command":"declare","action":"Steal","target_player_id":2,"thoughts":"This target has coins and may be vulnerable."}
{"command":"respond","response":"pass","thoughts":"A challenge is too risky here."}
{"command":"respond","response":"challenge","thoughts":"The claim conflicts with the public action history."}
{"command":"respond","response":"block","thoughts":"Blocking preserves my influence."}
{"command":"select_card","card":"Duke","thoughts":"This is the weaker card for my current position."}
{"command":"select_card","keep_cards":["Ambassador","Captain"],"thoughts":"These cards preserve flexible actions and blocks."}
{"command":"noop"}

Prefer actions that improve your chance to win, but stay valid for the current
phase and player.

Rule notes for this game variant:
- Players holding Duke cannot take Foreign Aid.
- Foreign Aid can be challenged; a challenge means "I think you have Duke."
- Foreign Aid can also be blocked by a player claiming Duke.
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
        "thoughts": {"type": "string"},
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


def _post_json(
    url: str,
    payload: dict,
    headers: dict,
    timeout: int = 180,
    max_retries: int = 2,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AgentAPIError(f"LLM API returned HTTP {exc.code}: {body}") from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(2 ** attempt)

    if isinstance(last_error, urllib.error.URLError):
        detail = last_error.reason
    else:
        detail = last_error
    raise AgentAPIError(f"Could not reach LLM API after {max_retries + 1} attempt(s): {detail}")


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


def safe_fallback_decision(private_view: dict) -> dict:
    legal_next = private_view.get("legal_next", {})

    selection = legal_next.get("selection")
    if selection:
        if selection["kind"] == "lose_influence":
            return {"command": "select_card", "card": selection["cards"][0]}
        if selection["kind"] == "exchange":
            return {
                "command": "select_card",
                "keep_cards": selection["candidates"][:selection["keep_count"]],
            }

    responses = legal_next.get("responses") or []
    if responses:
        return {"command": "respond", "response": "pass"}

    declarations = legal_next.get("declarations") or []
    for preferred_action in ("Coup", "Income", "Foreign Aid", "Tax", "Exchange", "Steal", "Assassinate"):
        for declaration in declarations:
            if declaration["action"] != preferred_action:
                continue
            decision = {"command": "declare", "action": preferred_action}
            if declaration.get("requires_target"):
                targets = declaration.get("valid_target_ids") or []
                if targets:
                    decision["target_player_id"] = targets[0]
            return decision

    return {"command": "noop"}


class CoupLLMAgent:
    provider = None
    model = None

    def build_user_prompt(self, private_view: dict, retry_error: str | None = None) -> str:
        return json.dumps(
            {
                "task": "Choose the next Coup command for this player.",
                "important": (
                    "Return one command from private_view.legal_next exactly. "
                    "There is no provider-side chat memory; use private_view.history for previous turns."
                ),
                "retry_error": retry_error,
                "private_view": private_view,
            },
            sort_keys=True,
        )

    def _parse_decision_result(self, raw_output: str, private_view: dict) -> dict:
        raw_decision = _extract_json_object(raw_output)
        thoughts = raw_decision.get("thoughts")
        if thoughts is not None and not isinstance(thoughts, str):
            thoughts = json.dumps(thoughts)
        return {
            "decision": normalize_decision(raw_decision, private_view),
            "thoughts": thoughts,
            "raw_output": raw_output,
        }

    def decide(self, private_view: dict) -> dict:
        retry_error = None
        raw_output = None
        for attempt in range(2):
            try:
                raw_output = self._call_model(private_view, retry_error=retry_error)
                parsed = self._parse_decision_result(raw_output, private_view)
                return {
                    "provider": self.provider,
                    "model": self.model,
                    **parsed,
                    "fallback": False,
                }
            except AgentAPIError as exc:
                retry_error = str(exc)
                if attempt == 0:
                    continue

        return {
            "provider": self.provider,
            "model": self.model,
            "decision": safe_fallback_decision(private_view),
            "thoughts": f"I returned an illegal move twice, so the runner used a safe legal fallback: {retry_error}",
            "raw_output": raw_output,
            "fallback": True,
        }

    def _call_model(self, private_view: dict, retry_error: str | None = None) -> str:
        raise NotImplementedError
