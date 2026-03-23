"""
SkillLoader — reads agent skill definitions from Markdown files.

File format
───────────
Each skill file is a Markdown document with a YAML frontmatter block:

    ---
    name: MyAgent
    display_name: My Agent Display Name
    model: gpt-4o
    tools:
      - tool_name_one
      - tool_name_two
    ---

    # Agent Title

    Instructions in plain Markdown...

The frontmatter keys are:
  name         (required) Python identifier used when building the Agent.
  display_name (optional) Human-readable label for logs / UI.
  model        (optional) OpenAI model ID.  Defaults to DEFAULT_MODEL.
  tools        (optional) List of tool names resolvable via ToolRegistry.

Usage
─────
    from skills.skill_loader import SkillLoader

    skill = SkillLoader.load("new_volume_agent")
    agent = skill.build()        # returns an openai-agents Agent
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from agents import Agent

from workflow.tools.tool_registry import ToolRegistry

SKILLS_DIR    = Path(__file__).parent
DEFAULT_MODEL = "gpt-4o"


# ---------------------------------------------------------------------------
# Skill data class
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    name: str
    display_name: str
    model: str
    tool_names: List[str]
    instructions: str
    source_file: Path
    raw_meta: Dict[str, Any] = field(default_factory=dict)

    # ── Agent builder ────────────────────────────────────────────────────────

    def build(self, tool_registry: Optional[ToolRegistry] = None) -> Agent:
        """Instantiate an openai-agents Agent from this skill definition."""
        registry = tool_registry or ToolRegistry.default()
        tools = registry.resolve(self.tool_names)

        return Agent(
            name=self.name,
            instructions=self.instructions,
            tools=tools,
            model=self.model,
        )

    # ── Repr / debug ─────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Skill(name={self.name!r}, model={self.model!r}, "
            f"tools={self.tool_names})"
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL,
)


def _parse_skill_file(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(
            f"Skill file '{path}' is missing a valid YAML frontmatter block.\n"
            "Expected format:\n---\nname: MyAgent\n...\n---\n\n# Instructions"
        )

    fm_text, body = m.group(1), m.group(2).strip()
    meta: Dict[str, Any] = yaml.safe_load(fm_text) or {}

    if "name" not in meta:
        raise ValueError(f"Skill file '{path}' frontmatter is missing required key 'name'.")

    return Skill(
        name=meta["name"],
        display_name=meta.get("display_name", meta["name"]),
        model=meta.get("model", DEFAULT_MODEL),
        tool_names=meta.get("tools", []),
        instructions=body,
        source_file=path,
        raw_meta=meta,
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class SkillLoader:
    """
    Loads Skill objects from .md files in the skills/ directory.

    Skills are cached after first load so repeated calls are cheap.
    """

    _cache: Dict[str, Skill] = {}

    @classmethod
    def load(cls, skill_name: str, skills_dir: Path = SKILLS_DIR) -> Skill:
        """
        Load a skill by its file stem (e.g. "new_volume_agent") or by its
        frontmatter `name` field (e.g. "NewVolumeAgent").

        Searches for `<skill_name>.md` first; falls back to scanning all files
        for a matching `name` frontmatter key.
        """
        cache_key = str(skills_dir / skill_name)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        # Try exact filename match first
        candidate = skills_dir / f"{skill_name}.md"
        if candidate.exists():
            skill = _parse_skill_file(candidate)
            cls._cache[cache_key] = skill
            return skill

        # Fall back: scan all .md files for matching name
        for md_file in sorted(skills_dir.glob("*.md")):
            try:
                skill = _parse_skill_file(md_file)
                if skill.name == skill_name:
                    cls._cache[cache_key] = skill
                    return skill
            except ValueError:
                pass

        raise FileNotFoundError(
            f"No skill found for '{skill_name}' in '{skills_dir}'.\n"
            f"Available: {cls.list_available(skills_dir)}"
        )

    @classmethod
    def load_all(cls, skills_dir: Path = SKILLS_DIR) -> Dict[str, Skill]:
        """Load every .md file in the skills directory. Returns {stem: Skill}."""
        result: Dict[str, Skill] = {}
        for md_file in sorted(skills_dir.glob("*.md")):
            try:
                skill = _parse_skill_file(md_file)
                result[md_file.stem] = skill
            except ValueError as e:
                # Non-skill .md files (READMEs etc.) are silently skipped
                import logging
                logging.getLogger(__name__).debug("Skipped '%s': %s", md_file.name, e)
        return result

    @classmethod
    def list_available(cls, skills_dir: Path = SKILLS_DIR) -> List[str]:
        return sorted(p.stem for p in skills_dir.glob("*.md"))

    @classmethod
    def invalidate_cache(cls) -> None:
        """Force re-read of all skill files on next load (useful in tests)."""
        cls._cache.clear()
