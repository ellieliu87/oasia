"""
Oasia — Configuration
Reads from .env file using python-dotenv.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).parent
load_dotenv(_project_root / ".env")


class Config:
    # Intex API
    INTEX_API_URL: str = os.getenv("INTEX_API_URL", "https://api.intex.com/v1")
    INTEX_API_KEY: str = os.getenv("INTEX_API_KEY", "")

    # OpenAI API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Data Paths
    MARKET_DATA_DIR: str = os.getenv("MARKET_DATA_DIR", str(_project_root / "data" / "market_data"))
    SNAPSHOT_DB_PATH: str = os.getenv("SNAPSHOT_DB_PATH", str(_project_root / "data" / "snapshots.db"))
    NEXUS_DB_PATH: str    = os.getenv("NEXUS_DB_PATH",    str(_project_root / "data" / "nexus_results.duckdb"))
    CACHE_DIR: str = os.getenv("CACHE_DIR", str(_project_root / "data" / "cache"))

    # Model Parameters
    N_RATE_PATHS: int = int(os.getenv("N_RATE_PATHS", "256"))
    PREPAY_MODEL_PATH: str = os.getenv("PREPAY_MODEL_PATH", str(_project_root / "data" / "models" / "prepay_model.pkl"))
    BGM_MODEL_PATH: str = os.getenv("BGM_MODEL_PATH", str(_project_root / "data" / "models" / "bgm_model.pkl"))
    TERM_STRUCTURE_PATH: str = os.getenv("TERM_STRUCTURE_PATH", str(_project_root / "data" / "market_data"))

    # Universe Configuration
    UNIVERSE_PRODUCT_TYPES: list = os.getenv("UNIVERSE_PRODUCT_TYPES", "CC30,CC15,GN30,GN15").split(",")

    # Risk Limits
    EVE_LIMIT_PCT: float = float(os.getenv("EVE_LIMIT_PCT", "-5.0"))

    # UI
    GRADIO_PORT: int = int(os.getenv("GRADIO_PORT", "7860"))

    # LDAP / Active Directory
    LDAP_SERVER:              str  = os.getenv("LDAP_SERVER", "ldap://your-ad-server.internal")
    LDAP_USE_SSL:             bool = os.getenv("LDAP_USE_SSL", "false").lower() == "true"
    # Template for the bind DN.  Use one of:
    #   {username}@yourcompany.com        (UPN format — most common)
    #   DOMAIN\\{username}               (down-level logon name)
    #   uid={username},ou=users,dc=co,dc=com  (LDAP DN format)
    LDAP_USER_DN_TEMPLATE:    str  = os.getenv("LDAP_USER_DN_TEMPLATE", "{username}@yourcompany.com")

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create necessary directories if they don't exist."""
        for d in [cls.MARKET_DATA_DIR, cls.CACHE_DIR, Path(cls.SNAPSHOT_DB_PATH).parent]:
            Path(d).mkdir(parents=True, exist_ok=True)

    @classmethod
    def has_intex_key(cls) -> bool:
        return bool(cls.INTEX_API_KEY)

    @classmethod
    def has_openai_key(cls) -> bool:
        return bool(cls.OPENAI_API_KEY)
