from contextlib import asynccontextmanager
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import settings
from .engine import EngineFailure, MaiaEngine
from .schemas import HealthResponse, MoveRequest, MoveResponse


engine = MaiaEngine(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.preload_model:
        await engine.start()
    yield
    await engine.close()


app = FastAPI(
    title="Gambet Maia Server",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API_KEY is not configured")
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    supplied = authorization[len(prefix):]
    if not hmac.compare_digest(supplied, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", model=settings.model, engine_started=engine.started)


@app.post("/v1/move", response_model=MoveResponse, dependencies=[Depends(require_api_key)])
async def move(request: MoveRequest) -> MoveResponse:
    try:
        return await engine.generate(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EngineFailure as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
