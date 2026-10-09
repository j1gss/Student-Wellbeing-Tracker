"""API tests. Run from the backend folder:  pip install pytest httpx2  then  pytest -q"""
import pytest
from fastapi.testclient import TestClient

import main

CHECKIN = dict(entry_date="2026-09-30", mood=3, stress=2, sleep_hours=7, study_hours=4,
               water_liters=2, exercise_mins=20, note="hi")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")  # fresh database per test
    main.init_db()
    return TestClient(main.app)


def signup(client, name="sam_1", pw="longenough"):
    r = client.post("/api/register", json={"username": name, "password": pw})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_no_token_is_refused(client):
    assert client.get("/api/history").status_code == 401


def test_wrong_password_is_refused(client):
    assert client.post("/api/login", json={"username": "demo", "password": "nope"}).status_code == 401


def test_weak_password_is_rejected(client):
    assert client.post("/api/register", json={"username": "sam", "password": "abc"}).status_code == 400


def test_duplicate_username_is_rejected(client):
    signup(client)
    r = client.post("/api/register", json={"username": "SAM_1", "password": "longenough"})
    assert r.status_code == 400


def test_invalid_mood_is_rejected(client):
    h = signup(client)
    assert client.post("/api/checkin", headers=h, json={**CHECKIN, "mood": 9}).status_code == 422


def test_note_over_60_characters_is_rejected(client):
    h = signup(client)
    assert client.post("/api/checkin", headers=h, json={**CHECKIN, "note": "x" * 61}).status_code == 422


def test_checkin_returns_a_prediction(client):
    h = signup(client)
    r = client.post("/api/checkin", headers=h, json=CHECKIN)
    assert r.status_code == 200 and 0 <= r.json()["predicted_productivity"] <= 100


def test_users_only_see_their_own_rows(client):
    a, b = signup(client, "user_a"), signup(client, "user_b")
    client.post("/api/checkin", headers=a, json=CHECKIN)
    assert len(client.get("/api/history", headers=a).json()) == 1
    assert client.get("/api/history", headers=b).json() == []


def test_delete_removes_only_own_rows(client):
    a, b = signup(client, "user_a"), signup(client, "user_b")
    client.post("/api/checkin", headers=a, json=CHECKIN)
    client.post("/api/checkin", headers=b, json=CHECKIN)
    assert client.delete("/api/data", headers=a).json()["deleted"] == 1
    assert len(client.get("/api/history", headers=b).json()) == 1
