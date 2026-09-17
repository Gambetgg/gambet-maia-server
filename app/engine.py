import asyncio
from dataclasses import dataclass
import logging
import re
import time

import chess

from .config import Settings
from .schemas import Candidate, MoveRequest, MoveResponse


INFO_RE = re.compile(
    r"multipv (?P<rank>\d+).*?score cp (?P<cp>-?\d+).*?wdl "
    r"(?P<w>\d+) (?P<d>\d+) (?P<l>\d+).*?pv (?P<move>[a-h][1-8][a-h][1-8][qrbn]?)"
)
logger = logging.getLogger("gambet.maia")


@dataclass
class EngineFailure(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


class MaiaEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.process: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.stderr_task: asyncio.Task | None = None

    @property
    def started(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self) -> None:
        if self.started:
            return
        args = [
            "maia3-uci", "--model", self.settings.model,
            "--use-uci-history", "--device", self.settings.device,
        ]
        args.append("--use-amp" if self.settings.use_amp else "--no-use-amp")
        logger.info("Starting Maia model=%s device=%s", self.settings.model, self.settings.device)
        started = time.perf_counter()
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.stderr_task = asyncio.create_task(self._drain_stderr())
        await self._send("uci")
        await self._read_until("uciok", self.settings.startup_timeout_seconds)
        await self._send("isready")
        await self._read_until("readyok", self.settings.startup_timeout_seconds)
        logger.info("Maia ready in %d ms", round((time.perf_counter() - started) * 1000))

    async def _drain_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return
        while True:
            raw = await self.process.stderr.readline()
            if not raw:
                return
            logger.warning("Maia stderr: %s", raw.decode(errors="replace").rstrip())

    async def close(self) -> None:
        if not self.process:
            return
        if self.process.returncode is None:
            try:
                await self._send("quit")
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except (TimeoutError, BrokenPipeError):
                self.process.kill()
                await self.process.wait()
        self.process = None
        if self.stderr_task:
            self.stderr_task.cancel()
            self.stderr_task = None

    async def restart(self) -> None:
        await self.close()
        await self.start()

    async def _send(self, command: str) -> None:
        if not self.process or not self.process.stdin:
            raise EngineFailure("Maia process is not running")
        self.process.stdin.write((command + "\n").encode())
        await self.process.stdin.drain()

    async def _read_until(self, marker: str, timeout_seconds: float) -> list[str]:
        if not self.process or not self.process.stdout:
            raise EngineFailure("Maia process is not running")

        async def read() -> list[str]:
            lines: list[str] = []
            while True:
                raw = await self.process.stdout.readline()
                if not raw:
                    raise EngineFailure("Maia exited unexpectedly; inspect Railway logs for stderr")
                line = raw.decode(errors="replace").strip()
                lines.append(line)
                if line.startswith(marker):
                    return lines

        try:
            return await asyncio.wait_for(read(), timeout=timeout_seconds)
        except TimeoutError as exc:
            raise EngineFailure(f"Maia timed out waiting for {marker}") from exc

    async def generate(self, request: MoveRequest) -> MoveResponse:
        board = request.board()
        if board.is_game_over():
            raise ValueError("the supplied position is already game over")
        if request.deadline_ms > self.settings.max_deadline_ms:
            raise ValueError("deadline exceeds server maximum")

        async with self.lock:
            if not self.started:
                await self.start()
            started = time.perf_counter()
            logger.info(
                "Generating move bot_elo=%d player_elo=%d multipv=%d deadline_ms=%d",
                request.bot_elo, request.player_elo, request.multi_pv, request.deadline_ms,
            )
            try:
                await self._send("ucinewgame")
                await self._send(f"setoption name SelfElo value {request.bot_elo}")
                await self._send(f"setoption name OppoElo value {request.player_elo}")
                await self._send(f"setoption name Temperature value {request.temperature}")
                await self._send(f"setoption name TopP value {request.top_p}")
                await self._send(f"setoption name MultiPV value {request.multi_pv}")
                if request.moves:
                    await self._send("position startpos moves " + " ".join(request.moves))
                else:
                    await self._send("position fen " + request.fen)
                await self._send("go nodes 1")
                lines = await self._read_until("bestmove", request.deadline_ms / 1000)
            except EngineFailure:
                await self.close()
                raise

            best_line = next(line for line in reversed(lines) if line.startswith("bestmove"))
            move = best_line.split()[1]
            try:
                parsed = chess.Move.from_uci(move)
            except ValueError as exc:
                raise EngineFailure(f"Maia returned malformed move: {move}") from exc
            if parsed not in board.legal_moves:
                raise EngineFailure(f"Maia returned illegal move: {move}")

            candidates: list[Candidate] = []
            for line in lines:
                match = INFO_RE.search(line)
                if match:
                    candidates.append(Candidate(
                        rank=int(match.group("rank")),
                        move=match.group("move"),
                        cp=int(match.group("cp")),
                        wdl=(int(match.group("w")), int(match.group("d")), int(match.group("l"))),
                    ))
            candidates.sort(key=lambda item: item.rank)
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            logger.info("Maia returned %s in %d ms", move, elapsed_ms)
            return MoveResponse(
                move=move,
                model=self.settings.model,
                bot_elo=request.bot_elo,
                player_elo=request.player_elo,
                candidates=candidates,
                inference_ms=elapsed_ms,
            )
