from pydantic import BaseModel, Field, field_validator
import chess


class MoveRequest(BaseModel):
    fen: str
    moves: list[str] = Field(default_factory=list, max_length=600)
    bot_elo: int = Field(default=1500, ge=600, le=3000)
    player_elo: int = Field(default=1500, ge=600, le=3000)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    multi_pv: int = Field(default=5, ge=1, le=10)
    deadline_ms: int = Field(default=5000, ge=250, le=15000)

    @field_validator("fen")
    @classmethod
    def valid_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("fen must be a valid six-field FEN") from exc
        return value

    @field_validator("moves")
    @classmethod
    def valid_history(cls, moves: list[str]) -> list[str]:
        if not moves:
            return moves
        board = chess.Board()
        for raw in moves:
            try:
                move = chess.Move.from_uci(raw)
            except ValueError as exc:
                raise ValueError(f"invalid UCI move in history: {raw}") from exc
            if move not in board.legal_moves:
                raise ValueError(f"illegal move in history: {raw}")
            board.push(move)
        return moves

    def board(self) -> chess.Board:
        expected = chess.Board(self.fen)
        if self.moves:
            replay = chess.Board()
            for raw in self.moves:
                replay.push_uci(raw)
            if replay.fen() != expected.fen():
                raise ValueError("moves do not reconstruct the supplied FEN")
        return expected


class Candidate(BaseModel):
    rank: int
    move: str
    cp: int | None = None
    wdl: tuple[int, int, int] | None = None


class MoveResponse(BaseModel):
    move: str
    model: str
    bot_elo: int
    player_elo: int
    candidates: list[Candidate]
    inference_ms: int


class HealthResponse(BaseModel):
    status: str
    model: str
    engine_started: bool
