"""Main agent for SupplyNet."""

from src.common import BaseAgent, SupplynetTask


SYSTEM_PROMPT = """You are SupplyNet, an expert agent.

Your job: handle the task at hand using the tools available to you.
Be specific, accurate, and concise.
"""


class SupplynetAgent(BaseAgent):
    NAME = "crewai"

    def handle(self, task: SupplynetTask, message: str = "") -> str:
        return self.invoke_claude(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message or "Begin."}],
        )
