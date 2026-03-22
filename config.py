"""Load user configuration from ~/.email-agent/config.yaml."""

import yaml
from pathlib import Path

CONFIG_DIR = Path.home() / ".email-agent"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CREDENTIALS_FILE = CONFIG_DIR / "client_secret.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
KNOWLEDGE_BASE_DIR = CONFIG_DIR / "knowledge_base"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Defaults for optional config fields
_DEFAULTS = {
    "user_name": "User",
    "email": "",
    "sign_off": "Best wishes",
    "sign_off_casual": "Best",
    "user_title": "",
    "auto_trash_senders": [],
    "auto_archive_senders": [],
    "cc_rules": [],
    "escalation_keywords": [
        "media", "press", "journalist", "reporter", "interview",
        "partnership", "sponsor", "corporate",
        "complaint", "frustrated", "disappointed", "unacceptable",
    ],
    "category_keywords": {},
}


def load_config() -> dict:
    """Load config from ~/.email-agent/config.yaml, with sensible defaults."""
    config = dict(_DEFAULTS)

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                user_config = yaml.safe_load(f) or {}
            config.update(user_config)
        except yaml.YAMLError as e:
            raise RuntimeError(
                f"Invalid YAML in {CONFIG_FILE}. Please fix the syntax error:\n{e}"
            )

    return config


def get_sign_off(config: dict, casual: bool = False) -> str:
    """Return the appropriate sign-off block."""
    sign_off = config.get("sign_off_casual" if casual else "sign_off", "Best wishes")
    name = config["user_name"]
    title = config.get("user_title", "")

    if casual:
        return f"{sign_off},\n{name}"

    lines = [f"{sign_off},", name]
    if title:
        lines.append(title)
    return "\n".join(lines)
