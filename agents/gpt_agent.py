try:
    from .base import CoupLLMAgent, DECISION_SCHEMA, SYSTEM_PROMPT, AgentAPIError, get_env_value, _post_json
except ImportError:
    from base import CoupLLMAgent, DECISION_SCHEMA, SYSTEM_PROMPT, AgentAPIError, get_env_value, _post_json


class GPTAgent(CoupLLMAgent):
    provider = "openai"
    model = "gpt-5.5"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_env_value("OPENAI_API_KEY")
        if not self.api_key:
            raise AgentAPIError("OPENAI_API_KEY is required in the environment or .env to use the GPT agent.")

    def _call_model(self, private_view: dict) -> str:
        payload = {
            "model": self.model,
            "reasoning": {"effort": "high"},
            "instructions": SYSTEM_PROMPT,
            "input": self.build_user_prompt(private_view),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "coup_agent_decision",
                    "schema": DECISION_SCHEMA,
                    "strict": False,
                }
            },
        }
        response = _post_json(
            "https://api.openai.com/v1/responses",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        output_text = response.get("output_text")
        if output_text:
            return output_text

        for item in response.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text") and content.get("text"):
                    return content["text"]

        raise AgentAPIError("OpenAI response did not include text output.")
