import anthropic

try:
    from .base import CoupLLMAgent, DECISION_SCHEMA, SYSTEM_PROMPT, AgentAPIError, get_env_value
except ImportError:
    from base import CoupLLMAgent, DECISION_SCHEMA, SYSTEM_PROMPT, AgentAPIError, get_env_value


class ClaudeAgent(CoupLLMAgent):
    provider = "anthropic"
    model = "claude-sonnet-5"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_env_value("ANTHROPIC_API_KEY") or get_env_value("CLAUDE_API_KEY")
        if not self.api_key:
            raise AgentAPIError(
                "ANTHROPIC_API_KEY (or CLAUDE_API_KEY) is required in the environment or .env to use the Claude agent."
            )
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def _call_model(self, private_view: dict) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {
                    "type": "json_schema",
                    "schema": DECISION_SCHEMA,
                },
            },
            messages=[{"role": "user", "content": self.build_user_prompt(private_view)}],
        )

        for block in response.content:
            if block.type == "text":
                return block.text

        raise AgentAPIError("Claude response did not include text output.")
