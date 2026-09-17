import os
os.environ.setdefault("API_KEY", "test-secret")
os.environ.setdefault("PRELOAD_MODEL", "false")

from fastapi.testclient import TestClient
from app.main import app, engine
from app.engine import INFO_RE
from app.config import Settings
from app.schemas import MoveResponse


class FakeEngine:
    started = True

    async def generate(self, request):
        return MoveResponse(
            move="e2e4", model="maia3-5m", bot_elo=request.bot_elo,
            player_elo=request.player_elo, candidates=[], inference_ms=12,
        )

    async def close(self):
        return None


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_move_requires_key():
    with TestClient(app) as client:
        response = client.post("/v1/move", json={"fen": "startpos"})
    assert response.status_code in {401, 422}


def test_move(monkeypatch):
    monkeypatch.setattr("app.main.engine", FakeEngine())
    payload = {"fen": "rn1qkbnr/ppp2ppp/3b4/3pp3/8/3P1N2/PPP1PPPP/RNBQKB1R w KQkq - 0 4"}
    with TestClient(app) as client:
        response = client.post(
            "/v1/move", json=payload,
            headers={"Authorization": "Bearer test-secret"},
        )
    assert response.status_code == 200
    assert response.json()["move"] == "e2e4"


def test_parses_maia_candidate_line():
    line = "info depth 1 multipv 2 score cp -18 wdl 280 410 310 pv g1f3"
    match = INFO_RE.search(line)
    assert match is not None
    assert match.group("rank") == "2"
    assert match.group("move") == "g1f3"


def test_engine_uses_fast_persistent_worker():
    from app.engine import MaiaEngine

    command = MaiaEngine(Settings(torch_threads=3))._command()
    assert command[:3] == ["python", "-m", "app.fast_uci"]
    assert "--local-files-only" in command
    assert command[command.index("--threads") + 1] == "3"
