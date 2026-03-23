from agents import Agent
from workflow.skills.skill_loader import SkillLoader


def build_new_volume_agent() -> Agent:
    return SkillLoader.load("new_volume_agent").build()
