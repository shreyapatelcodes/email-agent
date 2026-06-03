"""Reading list storage and management for the article library."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from config import CONFIG_DIR

READING_LIST_FILE = CONFIG_DIR / "reading_list.json"
LIBRARY_DIR = Path(__file__).parent / "library"


def _load_data() -> dict:
    if READING_LIST_FILE.exists():
        with open(READING_LIST_FILE) as f:
            return json.load(f)
    return {"articles": []}


def _save_data(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(READING_LIST_FILE, "w") as f:
        json.dump(data, f, indent=2)
    _export_site_data(data)


def _export_site_data(data: dict):
    """Write data.js for the library website."""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    js_path = LIBRARY_DIR / "data.js"
    js_path.write_text(f"const LIBRARY_DATA = {json.dumps(data, indent=2)};")


def save_article(
    url: str,
    title: str = "",
    author: str = "",
    source: str = "",
    summary: str = "",
    topics: list[str] | None = None,
    notes: str = "",
    status: str = "unread",
    tagged_for: list[str] | None = None,
) -> dict:
    data = _load_data()
    article = {
        "id": str(uuid.uuid4())[:8],
        "url": url,
        "title": title,
        "author": author,
        "source": source,
        "date_saved": datetime.now().strftime("%Y-%m-%d"),
        "date_read": None,
        "status": status,
        "summary": summary,
        "notes": notes,
        "topics": topics or [],
        "tagged_for": tagged_for or [],
    }
    data["articles"].insert(0, article)
    _save_data(data)
    return article


def update_article(article_id: str, **fields) -> dict | None:
    data = _load_data()
    for article in data["articles"]:
        if article["id"] == article_id:
            if "status" in fields and fields["status"] == "read" and article["status"] != "read":
                fields["date_read"] = datetime.now().strftime("%Y-%m-%d")
            article.update(fields)
            _save_data(data)
            return article
    return None


def remove_article(article_id: str) -> bool:
    data = _load_data()
    original_len = len(data["articles"])
    data["articles"] = [a for a in data["articles"] if a["id"] != article_id]
    if len(data["articles"]) < original_len:
        _save_data(data)
        return True
    return False


def list_articles(
    status: str | None = None,
    topic: str | None = None,
    tagged_for: str | None = None,
) -> list[dict]:
    data = _load_data()
    articles = data["articles"]

    if status:
        articles = [a for a in articles if a["status"] == status]
    if topic:
        topic_lower = topic.lower()
        articles = [a for a in articles if any(topic_lower in t.lower() for t in a.get("topics", []))]
    if tagged_for:
        name_lower = tagged_for.lower()
        articles = [a for a in articles if any(name_lower in p.lower() for p in a.get("tagged_for", []))]

    return articles


def get_all_topics() -> list[str]:
    data = _load_data()
    topics = set()
    for article in data["articles"]:
        for t in article.get("topics", []):
            topics.add(t)
    return sorted(topics)


def get_all_people() -> list[str]:
    data = _load_data()
    people = set()
    for article in data["articles"]:
        for p in article.get("tagged_for", []):
            people.add(p)
    return sorted(people)


def get_graph_data() -> dict:
    """Build nodes and edges for the knowledge graph."""
    data = _load_data()
    articles = data["articles"]

    topic_set = set()
    for a in articles:
        for t in a.get("topics", []):
            topic_set.add(t)

    nodes = []
    edges = []

    for t in topic_set:
        nodes.append({"id": f"topic:{t}", "label": t, "type": "topic"})

    for a in articles:
        nodes.append({
            "id": f"article:{a['id']}",
            "label": a.get("title", a["url"]),
            "type": "article",
            "data": a,
        })
        for t in a.get("topics", []):
            edges.append({
                "source": f"article:{a['id']}",
                "target": f"topic:{t}",
            })

    # Connect topics that share articles (weighted by overlap count)
    from collections import Counter
    topic_pairs = Counter()
    for a in articles:
        topics = a.get("topics", [])
        for i, t1 in enumerate(topics):
            for t2 in topics[i + 1:]:
                pair = tuple(sorted([t1, t2]))
                topic_pairs[pair] += 1

    for (t1, t2), weight in topic_pairs.items():
        edges.append({
            "source": f"topic:{t1}",
            "target": f"topic:{t2}",
            "weight": weight,
            "type": "topic_link",
        })

    return {"nodes": nodes, "edges": edges}


def rebuild_site():
    """Force-rebuild the library site data file."""
    data = _load_data()
    _export_site_data(data)
