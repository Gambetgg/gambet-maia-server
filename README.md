# Gambet Maia Server

Private HTTP service that runs Maia 3 for Gambet practice games. It starts a persistent Maia UCI process and returns a legal human-like chess move.

## Deploy on Railway

1. Open https://railway.com/new and choose **Deploy from GitHub repo**.
2. Select `Gambetgg/gambet-maia-server`.
3. In **Variables**, add `API_KEY` with a long random value.
4. Keep `MAIA_MODEL=maia3-5m` for the first deployment.
5. Open **Settings**, choose **Networking**, and generate a public domain.
6. Visit `https://YOUR-DOMAIN/health`. It should return `status: ok`.

The initial build downloads the Maia 3 5M checkpoint, so it can take several minutes. The model remains loaded between requests.

## Request a move

```bash
curl -X POST "https://YOUR-DOMAIN/v1/move" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "bot_elo":1500,
    "player_elo":1500,
    "temperature":0.8,
    "top_p":0.95,
    "multi_pv":5,
    "deadline_ms":5000
  }'
```

If `moves` is supplied, it must contain the complete legal UCI move history from the normal starting position and must reconstruct the supplied FEN.

## Lovable connection

Do not call this service directly from browser code. Create a Supabase Edge Function that reads the authoritative game position, calls `/v1/move` with the private API key, verifies the returned move, and commits it to the game record.

Save these Supabase secrets:

```text
MAIA_API_URL=https://YOUR-DOMAIN
MAIA_API_KEY=YOUR_API_KEY
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export API_KEY=local-secret
export PRELOAD_MODEL=false
uvicorn app.main:app --reload
```

Run validation tests:

```bash
pytest -q
```

## Current scope

- Maia 3 normal practice moves
- Adjustable bot and player Elo
- Temperature and Top P sampling
- Candidate UCI lines for a future Stockfish filter
- Bearer-token authentication
- FEN and move-history validation
- One persistent serialized Maia worker per service instance

Stockfish-assisted elite mode and the Supabase Edge Function are the next stage after this service is deployed and tested.

## License

This repository is provided under GNU AGPL version 3 because it is a network service built around Maia 3. See `LICENSE` and `NOTICE.md`. This is not legal advice; confirm checkpoint and deployment terms before commercial release.
