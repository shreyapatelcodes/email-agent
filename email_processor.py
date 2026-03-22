"""Email classification and processing logic."""

from gmail_client import (
    fetch_unread_emails,
    fetch_thread,
    trash_email,
    archive_email,
)


def process_inbox(service, config):
    """Fetch unread emails, auto-clean spam/notifications, classify the rest.

    Returns a dict with counts and grouped emails:
      - trashed: count of auto-trashed emails
      - archived: count of auto-archived emails
      - groups.simple: thank yous, auto-replies (archive candidates)
      - groups.drafts: emails needing a reply, with thread context
      - groups.escalations: emails needing human attention
    """
    emails = fetch_unread_emails(service)

    auto_trash = config.get("auto_trash_senders", [])
    auto_archive = config.get("auto_archive_senders", [])
    escalation_keywords = config.get("escalation_keywords", [])
    category_keywords = config.get("category_keywords", {})

    trashed_count = 0
    archived_count = 0
    simple = []
    drafts = []
    escalations = []

    for email in emails:
        sender = email["from_email"]

        # Auto-trash spam (match full address or @domain)
        if any(sender == s or sender.endswith("@" + s) or sender.endswith("." + s) for s in auto_trash):
            trash_email(service, email["id"])
            trashed_count += 1
            continue

        # Auto-archive notifications (match full address or @domain)
        if any(sender == s or sender.endswith("@" + s) or sender.endswith("." + s) for s in auto_archive):
            archive_email(service, email["id"])
            archived_count += 1
            continue

        # Classify remaining emails
        body_lower = email["body"].lower().strip()
        subject_lower = email["subject"].lower().strip()

        # Simple: thank yous, auto-replies, out-of-office
        is_thank_you = (
            len(body_lower) < 200
            and any(w in body_lower for w in ["thank you", "thanks", "thank u"])
            and "?" not in body_lower
        )
        is_auto_reply = any(
            phrase in subject_lower
            for phrase in ["auto-reply", "automatic reply", "out of office", "out-of-office"]
        )

        if is_thank_you or is_auto_reply:
            simple.append({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "summary": body_lower[:100],
            })
            continue

        # Escalations
        is_escalation = any(
            kw in body_lower or kw in subject_lower for kw in escalation_keywords
        )

        if is_escalation:
            escalations.append({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "body": email["body"],
            })
            continue

        # Needs a draft reply — fetch thread for context
        thread_messages = fetch_thread(service, email["threadId"])

        # Determine category
        category = "general"
        for cat, keywords in category_keywords.items():
            if any(kw in body_lower or kw in subject_lower for kw in keywords):
                category = cat
                break

        drafts.append({
            "id": email["id"],
            "threadId": email["threadId"],
            "from": email["from"],
            "from_email": email["from_email"],
            "to": email["to"],
            "subject": email["subject"],
            "body": email["body"],
            "thread": thread_messages,
            "category": category,
        })

    return {
        "trashed": trashed_count,
        "archived": archived_count,
        "groups": {
            "simple": simple,
            "drafts": drafts,
            "escalations": escalations,
        },
    }
