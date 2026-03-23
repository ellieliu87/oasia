from agents import Agent
from workflow.skills.skill_loader import SkillLoader


def build_risk_agent() -> Agent:
    return SkillLoader.load("risk_agent").build()
