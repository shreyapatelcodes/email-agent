"""Email classification and processing logic."""

import re

from gmail_client import (
    fetch_unread_emails,
    fetch_thread,
    trash_email,
    archive_email,
)

_URL_PATTERN = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)

_ARTICLE_DOMAINS = [
    "substack.com",
    "medium.com",
    "theatlantic.com",
    "newyorker.com",
    "nytimes.com",
    "theguardian.com",
    "aeon.co",
    "longreads.com",
    "lrb.co.uk",
    "nplusonemag.com",
    "theverge.com",
    "wired.com",
    "nautil.us",
    "lithub.com",
    "every.to",
]


def _extract_article_urls(text: str) -> list[str]:
    """Pull URLs that look like articles (not unsubscribe links, tracking pixels, etc.)."""
    urls = _URL_PATTERN.findall(text)
    skip = ["unsubscribe", "manage-subscription", "tracking", "click.", "list-manage", "mailchimp",
            "email.mg.", "mailto:", ".png", ".jpg", ".gif", "accounts.google"]
    filtered = []
    for url in urls:
        if any(s in url.lower() for s in skip):
            continue
        filtered.append(url)
    return filtered


def _is_article_email(email: dict, user_email: str) -> tuple[bool, list[str]]:
    """Detect if an email is a forwarded or self-sent article worth saving."""
    sender = email.get("from_email", "").lower()
    body = email.get("body", "")
    subject = email.get("subject", "").lower()

    urls = _extract_article_urls(body)
    if not urls:
        return False, []

    is_self_sent = sender == user_email.lower()

    is_from_article_domain = any(domain in sender for domain in _ARTICLE_DOMAINS)

    is_forwarded = subject.startswith("fwd:") or subject.startswith("fw:")

    has_article_url = any(
        any(domain in url.lower() for domain in _ARTICLE_DOMAINS)
        for url in urls
    )

    if is_self_sent or is_forwarded or is_from_article_domain or has_article_url:
        return True, urls

    return False, []


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

    user_email = config.get("email", "")
    auto_trash = config.get("auto_trash_senders", [])
    auto_archive = config.get("auto_archive_senders", [])
    escalation_keywords = config.get("escalation_keywords", [])
    category_keywords = config.get("category_keywords", {})

    trashed_count = 0
    archived_count = 0
    simple = []
    drafts = []
    escalations = []
    articles = []

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

        # Articles: self-sent links, forwards, or emails from article platforms
        is_article, article_urls = _is_article_email(email, user_email)
        if is_article:
            articles.append({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "body": email["body"],
                "urls": article_urls,
            })
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
            "articles": articles,
            "drafts": drafts,
            "escalations": escalations,
        },
    }
