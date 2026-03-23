from agents import Agent
from workflow.skills.skill_loader import SkillLoader


def build_allocation_agent() -> Agent:
    return SkillLoader.load("allocation_agent").build()
