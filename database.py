import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get(
    "MANGA_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mangas.db"),
)

VALID_STATUSES = ["Lendo", "Planejo Ler", "Pausado", "Concluído", "Dropado"]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(seed_if_empty: bool = True) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mangas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            chapter_read REAL NOT NULL DEFAULT 0,
            latest_chapter REAL DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'Lendo',
            rating INTEGER DEFAULT NULL,
            cover_url TEXT DEFAULT '',
            read_url TEXT DEFAULT '',
            release_day TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    if seed_if_empty:
        cursor.execute("SELECT COUNT(*) as total FROM mangas")
        row = cursor.fetchone()
        if row and row["total"] == 0:
            seed_initial_mangas(conn)

    conn.close()


def seed_initial_mangas(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc)
    initial_items = [
        {
            "title": "Doctor Resignation",
            "chapter_read": 30.0,
            "latest_chapter": 116.0,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "",
            "updated_at": (now - timedelta(hours=20)).isoformat(),
        },
        {
            "title": "Infinite Leveling: Murim",
            "chapter_read": 221.0,
            "latest_chapter": 281.0,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "",
            "updated_at": (now - timedelta(hours=22)).isoformat(),
        },
        {
            "title": "I Married the Dragon I Killed",
            "chapter_read": 15.0,
            "latest_chapter": 23.0,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "Cap. 15: You Can Sleep When You're Dead",
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "title": "If You Desire to Keep Me",
            "chapter_read": 74.0,
            "latest_chapter": 85.0,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "",
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "title": "Urenokori no Dorei Elf o Hirotta no de, Musume ni Suru Koto ni shita",
            "chapter_read": 12.1,
            "latest_chapter": 31.1,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "",
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "title": "Infinite Mage",
            "chapter_read": 103.0,
            "latest_chapter": 193.0,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "",
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "title": "I Will Divorce the Female Lead’s Siscon Brother",
            "chapter_read": 15.0,
            "latest_chapter": 112.0,
            "status": "Lendo",
            "rating": None,
            "cover_url": "",
            "read_url": "",
            "release_day": "",
            "notes": "",
            "updated_at": (now - timedelta(days=3)).isoformat(),
        },
    ]

    cursor = conn.cursor()
    for item in initial_items:
        cursor.execute(
            """
            INSERT INTO mangas (
                title, chapter_read, latest_chapter, status, rating,
                cover_url, read_url, release_day, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["title"],
                item["chapter_read"],
                item["latest_chapter"],
                item["status"],
                item["rating"],
                item["cover_url"],
                item["read_url"],
                item["release_day"],
                item["notes"],
                item["updated_at"],
            ),
        )
    conn.commit()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    chapter_read = float(d["chapter_read"] or 0)
    latest_chapter = float(d["latest_chapter"]) if d["latest_chapter"] is not None else None

    if latest_chapter is not None and latest_chapter > chapter_read:
        unread = round(latest_chapter - chapter_read, 2)
    else:
        unread = 0.0

    d["unread_chapters"] = unread
    return d


def parse_copied_bookmarks(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse bookmark text pasted from manga reader sites, e.g.:
    Doctor Resignation
    RemoveDoctor ResignationViewed : Chapter 30Current : Chapter 116Last updated : 20 hour ago
    """
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    results: List[Dict[str, Any]] = []

    detail_pattern = re.compile(
        r"^(?:Remove\s*)?(?P<inline_title>.*?)Viewed\s*:\s*(?P<viewed>.*?)"
        r"Current\s*:\s*(?P<current>.*?)(?:Last updated\s*:\s*(?P<updated>.*))?$",
        re.IGNORECASE,
    )

    def extract_chapter_and_note(text: str) -> tuple[float, str]:
        cleaned = text.strip()
        m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if not m:
            return 0.0, cleaned
        num = float(m.group(1))
        rest = cleaned[m.end() :].strip(" :-–—")
        note = f"Cap. {m.group(1)}: {rest}" if rest else ""
        return num, note

    prev_unmatched_line: Optional[str] = None

    for line in lines:
        m = detail_pattern.match(line)
        if m:
            inline_title = m.group("inline_title").strip()
            title = prev_unmatched_line if prev_unmatched_line else inline_title
            if not title:
                title = inline_title or "Mangá Sem Título"

            viewed_raw = m.group("viewed").strip()
            current_raw = m.group("current").strip()

            chapter_read, viewed_note = extract_chapter_and_note(viewed_raw)
            latest_chapter, _ = extract_chapter_and_note(current_raw)

            results.append(
                {
                    "title": title,
                    "chapter_read": chapter_read,
                    "latest_chapter": latest_chapter if latest_chapter > 0 else None,
                    "status": "Lendo",
                    "notes": viewed_note,
                }
            )
            prev_unmatched_line = None
        else:
            prev_unmatched_line = line

    return results
