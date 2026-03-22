# Email Agent

An MCP server that turns Claude Desktop into your email assistant. It connects to Gmail, reads your inbox, classifies emails, drafts replies in your voice, and sends them with your approval.

## What it does

- Fetches your unread emails and sorts them into groups: spam, notifications, simple replies, drafts, and escalations
- Auto-trashes spam and auto-archives notifications from senders you configure
- Drafts replies in your writing style using a customizable knowledge base
- Sends approved replies and archives handled emails
- All actions require your approval before anything is sent

## Prerequisites

- **Python 3.10+** (check with `python3 --version`)
- **A Gmail account**
- **Claude Desktop** ([download here](https://claude.ai/download))

## Setup

### 1. Set up Google Cloud credentials

This is the longest step, but you only do it once.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** at the top, then **New Project**. Name it anything (e.g. "Email Agent") and click **Create**
3. Make sure your new project is selected, then:
   - Go to **APIs & Services > Library** in the left sidebar
   - Search for **Gmail API** and click **Enable**
4. Set up the consent screen:
   - Go to **APIs & Services > OAuth consent screen**
   - Choose **External** and click **Create**
   - Fill in "App name" (e.g. "Email Agent") and your email for support/developer contact
   - Click through the Scopes page (no changes needed)
   - On the **Test users** page, click **Add users** and add your Gmail address
   - Click **Save and Continue**
5. Create your credentials:
   - Go to **APIs & Services > Credentials**
   - Click **Create Credentials > OAuth client ID**
   - Choose **Desktop app** as the application type
   - Click **Create**, then **Download JSON**
   - Save the file somewhere you can find it (your Downloads folder is fine)

### 2. Run the setup wizard

```bash
cd email-agent
python3 setup_wizard.py
```

The wizard will:
- Install Python dependencies
- Ask you to paste the path to the JSON file you downloaded
- Open your browser to sign in with Google
- Ask for your name, sign-off style, and spam/notification senders
- Print the config snippet for Claude Desktop

### 3. Add to Claude Desktop

Copy the config snippet the wizard prints and add it to your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

The snippet looks like this (the wizard fills in the correct paths for you):

```json
{
  "mcpServers": {
    "email-agent": {
      "command": "/path/to/python3",
      "args": ["/path/to/mcp_server.py"]
    }
  }
}
```

If you already have other MCP servers, just add the `"email-agent"` entry inside your existing `"mcpServers"` object.

### 4. Use it

Restart Claude Desktop, then say:

- **"Process my emails"** -- full workflow: fetch, classify, draft replies, send
- **"Check my inbox"** -- just see what's unread
- **"Send an email to ..."** -- compose and send a new email

## Configuration

Edit `~/.email-agent/config.yaml` to customize:

| Setting | What it does |
|---------|-------------|
| `auto_trash_senders` | Emails from these senders/domains go straight to trash |
| `auto_archive_senders` | Emails from these senders/domains get archived silently |
| `cc_rules` | Auto-CC someone when certain keywords appear in an email |
| `escalation_keywords` | Emails with these keywords are shown to you instead of auto-drafted |
| `category_keywords` | Custom categories for organizing draft replies |

For `auto_trash_senders` and `auto_archive_senders`, you can use full email addresses (`noreply@linkedin.com`) or just domains (`linkedin.com`).

## Knowledge Base

Put `.md` files in `~/.email-agent/knowledge_base/` to teach the agent your style and context:

| File | Purpose |
|------|---------|
| `tone.md` | How you write (included by default) |
| `corrections.md` | Learned corrections from edited drafts (auto-populated) |
| `faq.md` | Common questions and your preferred answers |
| `templates.md` | Reply templates by category |

## Troubleshooting

**"Run setup_wizard.py first"** -- You need to run the setup wizard before the MCP server will work. It creates the credentials and config files.

**OAuth error / "Access blocked"** -- Make sure you added your Gmail address as a test user in the Google Cloud Console (step 1.4 above).

**"Python 3.10+ required"** -- Your system Python is too old. Install a newer version via [python.org](https://www.python.org/downloads/), [Homebrew](https://brew.sh/) (`brew install python`), or [conda](https://docs.conda.io/).

**MCP server not showing up in Claude Desktop** -- Make sure the `command` path in your config points to the Python that has the dependencies installed. The setup wizard prints the correct path for you.

**Token expired** -- Restart the MCP server (restart Claude Desktop). If that doesn't work, delete `~/.email-agent/token.json` and run the wizard again.

## Requirements

- Python 3.10+
- A Gmail account
- Claude Desktop
