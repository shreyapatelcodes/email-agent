#!/usr/bin/env python3
"""Interactive setup wizard for the Email Agent MCP server."""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from config import CONFIG_DIR, CREDENTIALS_FILE, TOKEN_FILE, GMAIL_SCOPES

DEFAULTS_DIR = Path(__file__).parent / "defaults"


def print_step(n, text):
    print(f"\n{'='*60}")
    print(f"  Step {n}: {text}")
    print(f"{'='*60}\n")


def check_python_version():
    v = sys.version_info
    if v < (3, 10):
        print(f"Python 3.10+ is required. You have {v.major}.{v.minor}.{v.micro}")
        print("Please install a newer Python version and try again.")
        sys.exit(1)
    print(f"Python {v.major}.{v.minor}.{v.micro} -- OK")


def install_dependencies():
    req_file = Path(__file__).parent / "requirements.txt"
    print("Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"])
    print("Dependencies installed.")


def setup_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    kb_dir = CONFIG_DIR / "knowledge_base"
    if not kb_dir.exists():
        src = DEFAULTS_DIR / "knowledge_base"
        if src.exists():
            shutil.copytree(src, kb_dir)
            print(f"Copied default knowledge base to {kb_dir}")
        else:
            kb_dir.mkdir(parents=True, exist_ok=True)
    print(f"Config directory: {CONFIG_DIR}")


def setup_oauth():
    print("To connect your Gmail account, you need Google OAuth credentials.\n")
    print("If you don't have them yet, follow these steps:")
    print("  1. Go to https://console.cloud.google.com/")
    print("  2. Create a new project (or select an existing one)")
    print("  3. Enable the Gmail API:")
    print("     - Go to APIs & Services > Library")
    print("     - Search for 'Gmail API' and click Enable")
    print("  4. Set up the OAuth consent screen:")
    print("     - Go to APIs & Services > OAuth consent screen")
    print("     - Choose 'External' user type")
    print("     - Fill in the app name (e.g. 'Email Agent') and your email")
    print("     - Add your email as a test user")
    print("  5. Create OAuth credentials:")
    print("     - Go to APIs & Services > Credentials")
    print("     - Click 'Create Credentials' > 'OAuth client ID'")
    print("     - Choose 'Desktop app' as the application type")
    print("     - Download the JSON file")
    print()

    while True:
        path = input("Paste the path to your downloaded client_secret JSON file: ").strip()
        path = path.strip("'\"")  # Handle quoted paths
        src = Path(path).expanduser()
        if src.exists() and src.suffix == ".json":
            dest = CREDENTIALS_FILE
            shutil.copy2(src, dest)
            os.chmod(str(dest), 0o600)
            print(f"Copied to {dest}")
            break
        print(f"File not found or not a JSON file: {src}")
        print("Please try again.\n")

    # Run OAuth flow
    print("\nOpening browser for Google sign-in...")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), GMAIL_SCOPES
        )
        creds = flow.run_local_server(port=0)

        fd = os.open(str(TOKEN_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")

        # Test connection
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email = profile["emailAddress"]
        print(f"\nConnected as: {email}")
        return email
    except Exception as e:
        print(f"\nOAuth failed: {e}")
        print("You can retry by running this wizard again.")
        sys.exit(1)


def interactive_config(email):
    print("Let's set up your preferences.\n")

    name = input("What's your name? ").strip()
    if not name:
        name = "User"

    title = input("Your title (optional, press Enter to skip): ").strip()

    sign_off = input("How do you sign off emails? [Best wishes]: ").strip()
    if not sign_off:
        sign_off = "Best wishes"

    sign_off_casual = input("Casual sign-off for quick replies? [Best]: ").strip()
    if not sign_off_casual:
        sign_off_casual = "Best"

    print("\nSenders to always auto-trash (comma-separated, or press Enter to skip):")
    print("  Example: noreply@linkedin.com, marketing@somecompany.com")
    trash_input = input("  > ").strip()
    auto_trash = [s.strip() for s in trash_input.split(",") if s.strip()] if trash_input else []

    print("\nSenders to always auto-archive (comma-separated, or press Enter to skip):")
    print("  Example: notifications@github.com, noreply@stripe.com")
    archive_input = input("  > ").strip()
    auto_archive = [s.strip() for s in archive_input.split(",") if s.strip()] if archive_input else []

    config = {
        "user_name": name,
        "email": email,
        "sign_off": sign_off,
        "sign_off_casual": sign_off_casual,
        "auto_trash_senders": auto_trash,
        "auto_archive_senders": auto_archive,
    }
    if title:
        config["user_title"] = title

    return config


def write_config(config):
    import yaml
    config_path = CONFIG_DIR / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"\nConfig written to {config_path}")


def get_claude_desktop_config_path():
    """Return the Claude Desktop config path for the current OS."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def print_claude_desktop_instructions():
    server_path = Path(__file__).parent / "mcp_server.py"
    python_path = sys.executable  # Use the same Python that ran the wizard

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print()
    print("To use with Claude Desktop, add this to your config file:")
    print()

    config_path = get_claude_desktop_config_path()
    print(f"  File: {config_path}")
    print()

    snippet = {
        "mcpServers": {
            "email-agent": {
                "command": str(python_path),
                "args": [str(server_path)]
            }
        }
    }
    print(json.dumps(snippet, indent=2))
    print()
    print("If you already have other MCP servers configured, just add the")
    print('"email-agent" entry inside your existing "mcpServers" object.')
    print()
    print('Open Claude Desktop and say "process my emails" to get started!')


def main():
    print()
    print("  Email Agent -- Setup Wizard")
    print("  ~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print()

    print_step(1, "Check Python version")
    check_python_version()

    print_step(2, "Install dependencies")
    install_dependencies()

    print_step(3, "Create config directory")
    setup_config_dir()

    print_step(4, "Google OAuth setup")
    email = setup_oauth()

    print_step(5, "Configure preferences")
    config = interactive_config(email)

    print_step(6, "Save configuration")
    write_config(config)

    print_claude_desktop_instructions()


if __name__ == "__main__":
    main()
