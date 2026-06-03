"""MCP server for the Email Agent. Launched by Claude Desktop via stdio transport."""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from config import load_config, CONFIG_DIR, KNOWLEDGE_BASE_DIR, CONFIG_FILE, get_sign_off
from gmail_client import (
    get_gmail_service,
    fetch_unread_emails,
    fetch_thread,
    send_email as gmail_send_email,
    send_batch as gmail_send_batch,
    archive_email as gmail_archive_email,
    archive_batch as gmail_archive_batch,
    mark_read_batch as gmail_mark_read_batch,
    trash_email as gmail_trash_email,
)
from email_processor import process_inbox
from reading_list import (
    save_article as rl_save_article,
    update_article as rl_update_article,
    remove_article as rl_remove_article,
    list_articles as rl_list_articles,
    get_all_topics,
    get_all_people,
    get_graph_data,
    rebuild_site,
)

mcp = FastMCP(
    "email-agent",
    instructions="Email agent that reads, classifies, drafts, and sends Gmail messages.",
)


# ── Tools ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def fetch_unread(max_results: int = 100) -> str:
    """Fetch unread inbox emails. Returns a JSON list of email objects with id, threadId, date, from, subject, and body."""
    service = get_gmail_service()
    emails = fetch_unread_emails(service, max_results=max_results)
    return json.dumps(emails, indent=2)


@mcp.tool()
def process_emails() -> str:
    """Fetch all unread emails, auto-trash spam, auto-archive notifications, and classify the rest into simple/drafts/escalations groups. This is the main workflow entry point."""
    service = get_gmail_service()
    config = load_config()
    result = process_inbox(service, config)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_thread(thread_id: str) -> str:
    """Fetch the full message thread by thread ID. Returns all messages in chronological order."""
    service = get_gmail_service()
    messages = fetch_thread(service, thread_id)
    return json.dumps(messages, indent=2)


@mcp.tool()
def send_one_email(to: str, subject: str, body: str, cc: str = "", thread_id: str = "") -> str:
    """Send a single email. Provide cc and thread_id as empty strings if not needed."""
    service = get_gmail_service()
    result = gmail_send_email(
        service,
        to=to,
        subject=subject,
        body=body,
        cc=cc or None,
        thread_id=thread_id or None,
    )
    return json.dumps({"status": "sent", "id": result["id"]})


@mcp.tool()
def send_batch(emails_json: str) -> str:
    """Send multiple emails. Input is a JSON string: a list of objects with keys: to, subject, body, and optionally cc, thread_id, mark_read_id."""
    try:
        emails = json.loads(emails_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    service = get_gmail_service()
    result = gmail_send_batch(service, emails)
    return json.dumps(result, indent=2)


@mcp.tool()
def archive_email(msg_id: str) -> str:
    """Archive a single email by message ID (removes from inbox, keeps in All Mail)."""
    service = get_gmail_service()
    gmail_archive_email(service, msg_id)
    return json.dumps({"status": "archived", "id": msg_id})


@mcp.tool()
def archive_batch(msg_ids_json: str) -> str:
    """Archive multiple emails. Input is a JSON string: a list of message ID strings."""
    try:
        msg_ids = json.loads(msg_ids_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    service = get_gmail_service()
    result = gmail_archive_batch(service, msg_ids)
    return json.dumps(result, indent=2)


@mcp.tool()
def mark_read_batch(msg_ids_json: str) -> str:
    """Mark multiple emails as read. Input is a JSON string: a list of message ID strings."""
    try:
        msg_ids = json.loads(msg_ids_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    service = get_gmail_service()
    result = gmail_mark_read_batch(service, msg_ids)
    return json.dumps(result, indent=2)


@mcp.tool()
def trash_email(msg_id: str) -> str:
    """Move a single email to trash by message ID."""
    service = get_gmail_service()
    gmail_trash_email(service, msg_id)
    return json.dumps({"status": "trashed", "id": msg_id})


# ── Reading List Tools ────────────────────────────────────────────────────────


@mcp.tool()
def save_article(
    url: str,
    title: str = "",
    author: str = "",
    source: str = "",
    summary: str = "",
    topics_json: str = "[]",
    notes: str = "",
    status: str = "unread",
    tagged_for_json: str = "[]",
) -> str:
    """Save an article to the reading library. topics_json and tagged_for_json are JSON arrays of strings, e.g. '["AI", "culture"]' or '["Sara"]'."""
    try:
        topics = json.loads(topics_json)
    except json.JSONDecodeError:
        topics = []
    try:
        tagged_for = json.loads(tagged_for_json)
    except json.JSONDecodeError:
        tagged_for = []
    article = rl_save_article(
        url=url, title=title, author=author, source=source,
        summary=summary, topics=topics, notes=notes,
        status=status, tagged_for=tagged_for,
    )
    return json.dumps({"status": "saved", "article": article}, indent=2)


@mcp.tool()
def update_article(article_id: str, fields_json: str) -> str:
    """Update a saved article. fields_json is a JSON object with fields to update, e.g. '{"status": "read", "notes": "loved this"}'. Valid fields: title, author, source, summary, topics, notes, status (unread/read), tagged_for."""
    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    result = rl_update_article(article_id, **fields)
    if result:
        return json.dumps({"status": "updated", "article": result}, indent=2)
    return json.dumps({"error": f"Article {article_id} not found"})


@mcp.tool()
def remove_article(article_id: str) -> str:
    """Remove an article from the reading library."""
    if rl_remove_article(article_id):
        return json.dumps({"status": "removed", "id": article_id})
    return json.dumps({"error": f"Article {article_id} not found"})


@mcp.tool()
def list_saved_articles(status: str = "", topic: str = "", tagged_for: str = "") -> str:
    """List saved articles from the reading library. Filter by status (unread/read), topic, or person name. Leave filters empty to list all."""
    articles = rl_list_articles(
        status=status or None,
        topic=topic or None,
        tagged_for=tagged_for or None,
    )
    return json.dumps({"count": len(articles), "articles": articles}, indent=2)


@mcp.tool()
def get_library_stats() -> str:
    """Get reading library stats: total articles, topics, people tagged, read vs unread counts."""
    articles = rl_list_articles()
    topics = get_all_topics()
    people = get_all_people()
    read = sum(1 for a in articles if a["status"] == "read")
    unread = sum(1 for a in articles if a["status"] == "unread")
    return json.dumps({
        "total": len(articles),
        "read": read,
        "unread": unread,
        "topics": topics,
        "people": people,
    }, indent=2)


@mcp.tool()
def export_library_site() -> str:
    """Rebuild the library website data file so the site reflects current articles. Returns the path to open in a browser."""
    rebuild_site()
    from reading_list import LIBRARY_DIR
    index_path = LIBRARY_DIR / "index.html"
    return json.dumps({
        "status": "exported",
        "path": str(index_path),
        "hint": f"Open {index_path} in a browser, or run: python -m http.server 8000 -d {LIBRARY_DIR}",
    }, indent=2)


# ── Resources ──────────────────────────────────────────────────────────────────


@mcp.resource("email-agent://config")
def get_config() -> str:
    """The user's email agent configuration."""
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text()
    return "# No config found. Run setup_wizard.py first."


@mcp.resource("email-agent://knowledge/{filename}")
def get_knowledge(filename: str) -> str:
    """A file from the user's knowledge base (tone guides, corrections, FAQ, etc.)."""
    filepath = (KNOWLEDGE_BASE_DIR / filename).resolve()
    if not str(filepath).startswith(str(KNOWLEDGE_BASE_DIR.resolve())):
        return "# Access denied: path outside knowledge base directory"
    if filepath.exists():
        return filepath.read_text()
    return f"# Knowledge base file not found: {filename}"


# ── Prompts ────────────────────────────────────────────────────────────────────


@mcp.prompt()
def process_my_emails() -> str:
    """Full email processing workflow prompt. Fetches config to personalize instructions."""
    config = load_config()
    name = config["user_name"]
    sign_off = get_sign_off(config)
    sign_off_casual = get_sign_off(config, casual=True)
    title = config.get("user_title", "")

    # Load knowledge base files if they exist
    kb_section = ""
    if KNOWLEDGE_BASE_DIR.exists():
        for f in sorted(KNOWLEDGE_BASE_DIR.iterdir()):
            if f.suffix == ".md":
                kb_section += f"\n### {f.stem}\n{f.read_text()}\n"

    # Build CC rules section
    cc_section = ""
    cc_rules = config.get("cc_rules", [])
    if cc_rules:
        cc_section = "\n## CC Rules\n"
        for rule in cc_rules:
            keywords = ", ".join(rule["keywords"])
            cc_section += f"- When email mentions [{keywords}]: CC {rule['name']} at {rule['cc']}\n"

    return f"""You are an email assistant for {name}. You help manage their inbox by reading, classifying, drafting replies, and sending emails.

## How to process emails

1. Call the `process_emails` tool. This fetches all unread emails, auto-trashes spam, auto-archives notifications, and classifies the rest.

2. Present the **simple** group first (thank yous, auto-replies):
   - Show a numbered list: sender + subject
   - Ask: "Archive all? y/n" (or let the user pick specific ones to keep)
   - Archive approved ones via `archive_batch`

3. Present the **drafts** group:
   - For each email, use the knowledge base + thread context + category to draft a reply
   - Show all drafts as a numbered list with: sender, subject, brief summary, proposed reply
   - Ask for batch commands like: "approve all", "edit 3", "skip 2"
   - Send all approved drafts at once via `send_batch`

4. Present the **escalations** group:
   - Show full email text for each
   - Ask {name} what to do with each one

5. After all groups are handled, archive remaining processed emails via `archive_batch`

## Writing Style

- You ARE {name} when drafting emails. Write in first person.
- Warm, professional, and genuine.
- Never use em dashes.
- Standard sign-off:
{sign_off}
- Casual/quick sign-off:
{sign_off_casual}
{cc_section}
## Classification (for reference — `process_emails` handles auto-trash and auto-archive automatically)

**Escalate** (show the email, don't draft):
- Media/press inquiries
- Complaints or frustrated contacts
- Anything you're unsure about

**Archive with brief mention** (no reply needed):
- Simple "thank you" responses
- Auto-replies / out-of-office
{f"## Knowledge Base{kb_section}" if kb_section else ""}
"""


@mcp.prompt()
def save_articles_from_email() -> str:
    """Prompt for processing forwarded articles from email into the reading library."""
    config = load_config()
    name = config["user_name"]
    return f"""You are helping {name} save articles to their reading library.

When {name} forwards an article or sends a link:

1. Extract the URL from the email body
2. Read the article content (fetch the URL if needed)
3. Determine: title, author, source (e.g. "Substack", "The Atlantic")
4. Write a 2-3 sentence summary capturing the core argument or insight
5. Assign 2-4 topic tags (e.g. "AI", "Culture", "Psychology", "Cities")
6. Check if {name} included any personal notes in the email
7. Ask {name}:
   - Have you read this already, or is it for later? (sets status to "read" or "unread")
   - Tag this for anyone? (e.g. "Sara would like this")
8. Call `save_article` with all the extracted info

Keep topic tags consistent across articles. Reuse existing tags when they fit (call `get_library_stats` to see current tags). Prefer broad, reusable topics over narrow one-off tags.

When done, confirm what was saved and mention the article count in the library."""


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
