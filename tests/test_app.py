import os
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, temp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(temp_db)

    os.environ["MANGA_DB_PATH"] = temp_db
    import database
    import app as app_module

    database.DB_PATH = temp_db
    database.init_db(seed_if_empty=True)

    with TestClient(app_module.app) as c:
        yield c

    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_initial_seed_contains_user_mangas(client):
    res = client.get("/api/mangas")
    assert res.status_code == 200
    data = res.json()
    assert data["stats"]["total"] == 7
    titles = {item["title"] for item in data["items"]}
    assert "Doctor Resignation" in titles
    assert "Infinite Leveling: Murim" in titles
    assert "Urenokori no Dorei Elf o Hirotta no de, Musume ni Suru Koto ni shita" in titles

    elf = next(
        i for i in data["items"] if "Urenokori no Dorei Elf" in i["title"]
    )
    assert elf["chapter_read"] == 12.1
    assert elf["latest_chapter"] == 31.1
    assert elf["unread_chapters"] == 19.0


def test_crud_and_chapter_actions(client):
    # Create
    res = client.post(
        "/api/mangas",
        json={
            "title": "Solo Leveling",
            "chapter_read": 10,
            "latest_chapter": 15,
            "status": "Lendo",
            "rating": 9,
            "release_day": "Quarta",
        },
    )
    assert res.status_code == 201
    created = res.json()
    manga_id = created["id"]
    assert created["unread_chapters"] == 5.0

    # Increment +1
    res = client.patch(f"/api/mangas/{manga_id}/chapter", json={"delta": 1})
    assert res.status_code == 200
    assert res.json()["chapter_read"] == 11.0
    assert res.json()["unread_chapters"] == 4.0

    # Catch up ("Em dia")
    res = client.patch(f"/api/mangas/{manga_id}/chapter", json={"catch_up": True})
    assert res.status_code == 200
    assert res.json()["chapter_read"] == 15.0
    assert res.json()["unread_chapters"] == 0.0

    # Delete
    res = client.delete(f"/api/mangas/{manga_id}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True


def test_import_pasted_bookmarks(client):
    raw_text = """
Doctor Resignation
RemoveDoctor ResignationViewed : Chapter 45Current : Chapter 120Last updated : 2 hour ago
Novo Manga Teste
RemoveNovo Manga TesteViewed : Chapter 5: The BeginningCurrent : Chapter 18Last updated : 1 day ago
"""
    res = client.post("/api/mangas/import-text", json={"text": raw_text})
    assert res.status_code == 200
    summary = res.json()
    assert summary["updated"] == 1
    assert summary["inserted"] == 1

    all_items = client.get("/api/mangas").json()["items"]
    doc = next(i for i in all_items if i["title"] == "Doctor Resignation")
    assert doc["chapter_read"] == 45.0
    assert doc["latest_chapter"] == 120.0

    novo = next(i for i in all_items if i["title"] == "Novo Manga Teste")
    assert novo["chapter_read"] == 5.0
    assert novo["latest_chapter"] == 18.0
    assert "The Beginning" in novo["notes"]
