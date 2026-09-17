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

During deployment, the service loads Maia and completes a full startup inference before Railway marks it healthy. Player requests therefore use an already warmed model. Keep the Railway service continuously running; do not enable sleeping or serverless scale-to-zero for production practice games.

The Gambet worker uses one Maia3 model pass per move. Upstream Maia3 normally
runs a second pass to calculate candidate-specific WDL analysis; that analysis
does not change the selected move and is intentionally skipped for live games.
`MAIA_TORCH_THREADS` defaults to `2` and can be tuned to the Railway service's
allocated CPU count.

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
    "multi_pv":1,
    "deadline_ms":60000
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
- One Maia candidate line for fast practice play on CPU
- Bearer-token authentication
- FEN and move-history validation
- One persistent serialized Maia worker per service instance

Stockfish-assisted elite mode will require separate benchmarking and likely stronger compute before increasing MultiPV above 1.

## License

This repository is provided under GNU AGPL version 3 because it is a network service built around Maia 3. See `LICENSE` and `NOTICE.md`. This is not legal advice; confirm checkpoint and deployment terms before commercial release.
