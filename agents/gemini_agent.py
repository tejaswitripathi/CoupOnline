try:
    from .base import CoupLLMAgent, SYSTEM_PROMPT, AgentAPIError, get_env_value, _post_json
except ImportError:
    from base import CoupLLMAgent, SYSTEM_PROMPT, AgentAPIError, get_env_value, _post_json


class GeminiAgent(CoupLLMAgent):
    provider = "gemini"
    model = "gemini-3.5-flash"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_env_value("GEMINI_API_KEY")
        if not self.api_key:
            raise AgentAPIError("GEMINI_API_KEY is required in the environment or .env to use the Gemini agent.")

    def _call_model(self, private_view: dict) -> str:
        payload = {
            "model": self.model,
            "system_instruction": SYSTEM_PROMPT,
            "input": self.build_user_prompt(private_view),
            "generation_config": {
                "thinking_level": "high",
                "temperature": 0.7,
            },
        }
        response = _post_json(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            payload,
            {"x-goog-api-key": self.api_key},
        )
        output_text = response.get("output_text")
        if output_text:
            return output_text

        for step in response.get("steps", []):
            for part in step.get("content", []):
                if part.get("type") == "text" and part.get("text"):
                    return part["text"]

        raise AgentAPIError("Gemini response did not include text output.")
