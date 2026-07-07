from .gpt_agent import GPTAgent
from .gemini_agent import GeminiAgent


AGENTS = {
    "gpt": GPTAgent,
    "openai": GPTAgent,
    "gemini": GeminiAgent,
}
