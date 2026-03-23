"""
Skill Loader — parses markdown skill files from agent/skills/.

Skill files follow the same frontmatter convention as Claude Code skills:
  - YAML frontmatter between --- delimiters defines metadata
  - The markdown body after the second --- is the agent's system prompt

Example skill file:
    ---
    name: security-selection
    description: Screens MBS universe for relative value
    model: gpt-4o
    tools:
      - screen_securities
      - get_market_data
    max_tokens: 2048
    ---

    # Security Selection Agent
    You are a specialist MBS security selection analyst...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Skills directory is co-located with this file
_SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass
class AgentSkill:
    """Parsed representation of a markdown skill file."""

    name: str
    description: str
    model: str
    system_prompt: str              # full markdown body (the agent's instructions)
    tools: list[str] = field(default_factory=list)      # analytics tool names available to this agent
    sub_agents: list[str] = field(default_factory=list) # sub-agent names (orchestrator only)
    max_tokens: int = 2048
    quick_queries: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Split a markdown file into (frontmatter_dict, body).

    Frontmatter must be a YAML block between the first two '---' lines.
    Falls back to (empty dict, full text) if no frontmatter is found.
    """
    lines = text.splitlines()

    # Must start with ---
    if not lines or lines[0].strip() != "---":
        return {}, text

    # Find closing ---
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    frontmatter_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:]).strip()

    # Minimal YAML parser (handles str, int, list of strings)
    meta: dict = {}
    current_key: str | None = None
    current_list: list | None = None

    for line in frontmatter_lines:
        # List item
        if line.startswith("  - ") or line.startswith("- "):
            item = line.lstrip().lstrip("- ").strip()
            if current_list is not None:
                current_list.append(item)
            continue

        # Key: value
        match = re.match(r'^(\w[\w_-]*):\s*(.*)', line)
        if match:
            # Flush previous list
            if current_key and current_list is not None:
                meta[current_key] = current_list

            current_key = match.group(1)
            raw_val = match.group(2).strip()

            if raw_val == "":
                # Start of a list block
                current_list = []
                meta[current_key] = current_list
            else:
                current_list = None
                # Try int
                try:
                    meta[current_key] = int(raw_val)
                except ValueError:
                    # Try float
                    try:
                        meta[current_key] = float(raw_val)
                    except ValueError:
                        meta[current_key] = raw_val

    return meta, body


def load_skill(skill_name: str) -> AgentSkill:
    """
    Load a single skill by name from the skills directory.

    Parameters
    ----------
    skill_name : str
        Skill name as it appears in the filename, e.g. 'security_selection'
        or 'security-selection' (hyphens and underscores are normalised).

    Returns
    -------
    AgentSkill

    Raises
    ------
    FileNotFoundError
        If no matching skill file is found.
    """
    # Normalise: replace hyphens with underscores for filename lookup
    normalized = skill_name.replace("-", "_")
    skill_path = _SKILLS_DIR / f"{normalized}.md"

    if not skill_path.exists():
        available = [p.stem for p in _SKILLS_DIR.glob("*.md")]
        raise FileNotFoundError(
            f"Skill '{skill_name}' not found at {skill_path}. "
            f"Available skills: {available}"
        )

    text = skill_path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    return AgentSkill(
        name=meta.get("name", normalized),
        description=meta.get("description", ""),
        model=meta.get("model", "gpt-4o"),
        system_prompt=body,
        tools=meta.get("tools", []),
        sub_agents=meta.get("sub_agents", []),
        max_tokens=int(meta.get("max_tokens", 2048)),
        quick_queries=meta.get("quick_queries", []),
    )


def load_all_skills() -> dict[str, AgentSkill]:
    """
    Load every skill file from the skills/ directory.

    Returns
    -------
    dict[str, AgentSkill]
        Keyed by normalised skill name (underscores, not hyphens).
    """
    skills: dict[str, AgentSkill] = {}
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        try:
            skill = load_skill(path.stem)
            key = skill.name.replace("-", "_")
            skills[key] = skill
        except Exception as exc:
            import warnings
            warnings.warn(f"Could not load skill {path.name}: {exc}")
    return skills


def list_skill_names() -> list[str]:
    """Return names of all available skill files."""
    return [p.stem for p in sorted(_SKILLS_DIR.glob("*.md"))]
