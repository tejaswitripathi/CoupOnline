import json
import time

try:
    from .base import CoupLLMAgent, DECISION_SCHEMA, SYSTEM_PROMPT, AgentAPIError, get_env_value
except ImportError:
    from base import CoupLLMAgent, DECISION_SCHEMA, SYSTEM_PROMPT, AgentAPIError, get_env_value


class ClaudeAgent(CoupLLMAgent):
    provider = "anthropic"
    model = "claude-haiku-4-5"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_env_value("ANTHROPIC_API_KEY") or get_env_value("CLAUDE_API_KEY")
        if not self.api_key:
            raise AgentAPIError(
                "ANTHROPIC_API_KEY (or CLAUDE_API_KEY) is required in the environment or .env to use the Claude agent."
            )
        try:
            import anthropic
        except ImportError as exc:
            raise AgentAPIError("The anthropic package is required to use the Claude agent.") from exc
        self._client = anthropic.Anthropic(api_key=self.api_key)
        self._use_thinking = "haiku" not in self.model

    def _json_text(self, value) -> str | None:
        if not value or callable(value):
            return None
        try:
            return json.dumps(value)
        except TypeError:
            return None

    def _extract_text(self, response) -> str | None:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text

        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", None)
            block_text = getattr(block, "text", None)
            if block_type == "text" and block_text:
                return block_text
            block_input = getattr(block, "input", None)
            block_input_text = self._json_text(block_input)
            if block_input_text:
                return block_input_text
            block_json = getattr(block, "json", None)
            block_json_text = self._json_text(block_json)
            if block_json_text:
                return block_json_text
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return block["text"]
            block_input_text = self._json_text(block.get("input") if isinstance(block, dict) else None)
            if block_input_text:
                return block_input_text
            block_json_text = self._json_text(block.get("json") if isinstance(block, dict) else None)
            if block_json_text:
                return block_json_text

        return None

    def _thinking_not_supported(self, error: Exception) -> bool:
        return "adaptive thinking is not supported" in str(error).lower()

    def _call_once(self, private_view: dict) -> str | None:
        request = {
            "model": self.model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": DECISION_SCHEMA,
                },
            },
            "messages": [{"role": "user", "content": self.build_user_prompt(private_view)}],
        }
        if self._use_thinking:
            request["thinking"] = {"type": "enabled"}

        response = self._client.messages.create(**request)
        return self._extract_text(response)

    def _call_model(self, private_view: dict) -> str:
        last_error = None
        for attempt in range(3):
            try:
                text = self._call_once(private_view)
                if text:
                    return text
                last_error = "Claude response did not include text output."
            except Exception as exc:
                last_error = exc
                if self._use_thinking and self._thinking_not_supported(exc):
                    self._use_thinking = False
                    continue

            if attempt < 2:
                time.sleep(2 ** attempt)

        raise AgentAPIError(f"Claude response did not include text output after 3 attempt(s): {last_error}")
