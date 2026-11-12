import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import (
    VALID_STATUSES,
    get_connection,
    init_db,
    parse_copied_bookmarks,
    row_to_dict,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(seed_if_empty=True)
    yield


app = FastAPI(title="Manga Manager PoC", lifespan=lifespan)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class MangaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    chapter_read: float = Field(default=0.0, ge=0.0)
    latest_chapter: Optional[float] = Field(default=None, ge=0.0)
    status: str = Field(default="Lendo")
    rating: Optional[int] = Field(default=None, ge=1, le=10)
    cover_url: str = Field(default="")
    read_url: str = Field(default="")
    release_day: str = Field(default="")
    notes: str = Field(default="")


class MangaUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    chapter_read: Optional[float] = Field(default=None, ge=0.0)
    latest_chapter: Optional[float] = Field(default=None, ge=0.0)
    clear_latest_chapter: bool = Field(default=False)
    status: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=10)
    clear_rating: bool = Field(default=False)
    cover_url: Optional[str] = None
    read_url: Optional[str] = None
    release_day: Optional[str] = None
    notes: Optional[str] = None


class ChapterAction(BaseModel):
    delta: Optional[float] = None
    chapter_read: Optional[float] = Field(default=None, ge=0.0)
    latest_chapter: Optional[float] = Field(default=None, ge=0.0)
    catch_up: bool = False


class ImportTextPayload(BaseModel):
    text: str


class ImportJsonPayload(BaseModel):
    items: List[Dict[str, Any]]


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/mangas")
def list_mangas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mangas ORDER BY updated_at DESC, id DESC")
    rows = [row_to_dict(r) for r in cursor.fetchall()]
    conn.close()

    total = len(rows)
    by_status = {status: 0 for status in VALID_STATUSES}
    with_unread = 0
    total_unread_chapters = 0.0

    for item in rows:
        st = item["status"]
        if st in by_status:
            by_status[st] += 1
        if item["unread_chapters"] > 0:
            with_unread += 1
            total_unread_chapters += item["unread_chapters"]

    return {
        "items": rows,
        "stats": {
            "total": total,
            "by_status": by_status,
            "with_unread": with_unread,
            "total_unread_chapters": round(total_unread_chapters, 1),
        },
    }


@app.post("/api/mangas", status_code=201)
def create_manga(payload: MangaCreate):
    status = payload.status if payload.status in VALID_STATUSES else "Lendo"
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO mangas (
            title, chapter_read, latest_chapter, status, rating,
            cover_url, read_url, release_day, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.title.strip(),
            round(payload.chapter_read, 2),
            round(payload.latest_chapter, 2) if payload.latest_chapter is not None else None,
            status,
            payload.rating,
            payload.cover_url.strip(),
            payload.read_url.strip(),
            payload.release_day.strip(),
            payload.notes.strip(),
            now,
        ),
    )
    new_id = cursor.lastrowid
    conn.commit()

    cursor.execute("SELECT * FROM mangas WHERE id = ?", (new_id,))
    created = row_to_dict(cursor.fetchone())
    conn.close()
    return created


@app.put("/api/mangas/{manga_id}")
def update_manga(manga_id: int, payload: MangaUpdate):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mangas WHERE id = ?", (manga_id,))
    existing_row = cursor.fetchone()
    if not existing_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Mangá não encontrado")

    existing = dict(existing_row)

    title = payload.title.strip() if payload.title is not None else existing["title"]
    chapter_read = (
        round(payload.chapter_read, 2)
        if payload.chapter_read is not None
        else existing["chapter_read"]
    )

    if payload.clear_latest_chapter:
        latest_chapter = None
    elif payload.latest_chapter is not None:
        latest_chapter = round(payload.latest_chapter, 2)
    else:
        latest_chapter = existing["latest_chapter"]

    status = (
        payload.status
        if payload.status in VALID_STATUSES
        else existing["status"]
    )

    if payload.clear_rating:
        rating = None
    elif payload.rating is not None:
        rating = payload.rating
    else:
        rating = existing["rating"]

    cover_url = (
        payload.cover_url.strip()
        if payload.cover_url is not None
        else existing["cover_url"]
    )
    read_url = (
        payload.read_url.strip()
        if payload.read_url is not None
        else existing["read_url"]
    )
    release_day = (
        payload.release_day.strip()
        if payload.release_day is not None
        else existing["release_day"]
    )
    notes = (
        payload.notes.strip()
        if payload.notes is not None
        else existing["notes"]
    )
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        UPDATE mangas
        SET title = ?, chapter_read = ?, latest_chapter = ?, status = ?,
            rating = ?, cover_url = ?, read_url = ?, release_day = ?,
            notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            title,
            chapter_read,
            latest_chapter,
            status,
            rating,
            cover_url,
            read_url,
            release_day,
            notes,
            now,
            manga_id,
        ),
    )
    conn.commit()

    cursor.execute("SELECT * FROM mangas WHERE id = ?", (manga_id,))
    updated = row_to_dict(cursor.fetchone())
    conn.close()
    return updated


@app.patch("/api/mangas/{manga_id}/chapter")
def update_chapter(manga_id: int, action: ChapterAction):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mangas WHERE id = ?", (manga_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Mangá não encontrado")

    existing = dict(row)
    current_read = float(existing["chapter_read"] or 0.0)
    latest = (
        float(existing["latest_chapter"])
        if existing["latest_chapter"] is not None
        else None
    )

    if action.catch_up and latest is not None:
        new_read = latest
    elif action.chapter_read is not None:
        new_read = max(0.0, round(action.chapter_read, 2))
    elif action.delta is not None:
        # Preserve decimal fraction if incrementing by whole number, or snap nicely
        new_read = max(0.0, round(current_read + action.delta, 2))
    else:
        new_read = current_read

    if action.latest_chapter is not None:
        latest = max(0.0, round(action.latest_chapter, 2))

    # If user read past latest_chapter, bump latest_chapter automatically
    if latest is not None and new_read > latest:
        latest = new_read

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "UPDATE mangas SET chapter_read = ?, latest_chapter = ?, updated_at = ? WHERE id = ?",
        (new_read, latest, now, manga_id),
    )
    conn.commit()

    cursor.execute("SELECT * FROM mangas WHERE id = ?", (manga_id,))
    updated = row_to_dict(cursor.fetchone())
    conn.close()
    return updated


@app.delete("/api/mangas/{manga_id}")
def delete_manga(manga_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM mangas WHERE id = ?", (manga_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Mangá não encontrado")

    cursor.execute("DELETE FROM mangas WHERE id = ?", (manga_id,))
    conn.commit()
    conn.close()
    return {"deleted": True, "id": manga_id}


@app.post("/api/mangas/import-text")
def import_from_text(payload: ImportTextPayload):
    parsed = parse_copied_bookmarks(payload.text)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Nenhum mangá reconhecido no texto colado. Certifique-se de incluir linhas no formato 'Viewed : Chapter X Current : Chapter Y'.",
        )

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    inserted = 0
    updated = 0

    for item in parsed:
        cursor.execute(
            "SELECT * FROM mangas WHERE LOWER(title) = LOWER(?)",
            (item["title"],),
        )
        existing = cursor.fetchone()
        if existing:
            notes = existing["notes"] or item.get("notes", "")
            cursor.execute(
                """
                UPDATE mangas
                SET chapter_read = ?, latest_chapter = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item["chapter_read"],
                    item["latest_chapter"],
                    notes,
                    now,
                    existing["id"],
                ),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO mangas (
                    title, chapter_read, latest_chapter, status, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["title"],
                    item["chapter_read"],
                    item["latest_chapter"],
                    item.get("status", "Lendo"),
                    item.get("notes", ""),
                    now,
                ),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "total_processed": len(parsed)}


@app.get("/api/mangas/export")
def export_mangas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mangas ORDER BY id ASC")
    rows = [row_to_dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"exported_at": datetime.now(timezone.utc).isoformat(), "items": rows}


@app.post("/api/mangas/import-json")
def import_from_json(payload: ImportJsonPayload):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    inserted = 0
    updated = 0

    for raw in payload.items:
        title = str(raw.get("title", "")).strip()
        if not title:
            continue
        chapter_read = float(raw.get("chapter_read") or 0.0)
        latest_chapter = (
            float(raw["latest_chapter"])
            if raw.get("latest_chapter") is not None
            else None
        )
        status = raw.get("status") if raw.get("status") in VALID_STATUSES else "Lendo"
        rating = int(raw["rating"]) if raw.get("rating") else None
        cover_url = str(raw.get("cover_url") or "").strip()
        read_url = str(raw.get("read_url") or "").strip()
        release_day = str(raw.get("release_day") or "").strip()
        notes = str(raw.get("notes") or "").strip()

        cursor.execute(
            "SELECT id FROM mangas WHERE LOWER(title) = LOWER(?)", (title,)
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE mangas
                SET chapter_read = ?, latest_chapter = ?, status = ?, rating = ?,
                    cover_url = ?, read_url = ?, release_day = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    chapter_read,
                    latest_chapter,
                    status,
                    rating,
                    cover_url,
                    read_url,
                    release_day,
                    notes,
                    now,
                    existing["id"],
                ),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO mangas (
                    title, chapter_read, latest_chapter, status, rating,
                    cover_url, read_url, release_day, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    chapter_read,
                    latest_chapter,
                    status,
                    rating,
                    cover_url,
                    read_url,
                    release_day,
                    notes,
                    now,
                ),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated}
