from .gpt_agent import GPTAgent
from .gemini_agent import GeminiAgent
from .claude_agent import ClaudeAgent
from .easy1 import EmpiricalClaudeAgent
from .med1 import EmpiricalGPTAgent
from .hard1 import EmpiricalGeminiAgent


AGENTS = {
    "gpt": GPTAgent,
    "openai": GPTAgent,
    "gemini": GeminiAgent,
    "claude": ClaudeAgent,
    "anthropic": ClaudeAgent,
    "empirical": EmpiricalClaudeAgent,
    "claude-empirical": EmpiricalClaudeAgent,
    "easy": EmpiricalClaudeAgent,
    "gpt-empirical": EmpiricalGPTAgent,
    "med": EmpiricalGPTAgent,
    "gemini-empirical": EmpiricalGeminiAgent,
    "hard": EmpiricalGeminiAgent,
}
