"""Low-latency Maia3 UCI worker for Gambet.

Upstream Maia3 evaluates every candidate position with a second model pass to
produce candidate-specific WDL values. Gambet only requests one move during a
live game, so that second pass roughly doubles latency without affecting which
move is selected. This worker emits the current position's WDL from the primary
pass and returns the selected move immediately.
"""

import argparse

import torch
from torch.amp import autocast

from maia3.dataset import get_legal_moves_mask
from maia3.uci import (
    Maia3UCIEngine,
    parse_args,
    sample_from_logits,
    seed_everything,
    wdl_from_value_logits,
)


class FastMaia3UCIEngine(Maia3UCIEngine):
    @torch.inference_mode()
    def score_moves(self):
        if self.board.is_game_over():
            return None, []

        legal_mask = get_legal_moves_mask(self.board, self.all_moves_dict)
        if not bool(legal_mask.any()):
            return None, []

        tokens = self._tokens_from_history(self.history).unsqueeze(0).to(self.cfg.device)
        self_elos = torch.tensor([self.self_elo], dtype=torch.long, device=self.cfg.device)
        oppo_elos = torch.tensor([self.oppo_elo], dtype=torch.long, device=self.cfg.device)

        with autocast("cuda", enabled=self.cfg.use_amp and self.cfg.device.startswith("cuda")):
            move_logits, value_logits, _ = self.model(tokens, self_elos, oppo_elos)

        logits = move_logits[0].float()
        logits = logits.masked_fill(~legal_mask.to(self.cfg.device), float("-inf"))
        selected_index = sample_from_logits(logits, self.temperature, self.top_p)
        move = self._move_from_index(selected_index)
        if move is None:
            return None, []

        # This is the value of the current position, obtained at no extra model
        # cost. Move selection still uses Maia3's full human policy distribution.
        position_wdl = wdl_from_value_logits(value_logits[0])
        return move, [{"move": move, "policy": 1.0, "wdl": position_wdl}]


def main(argv=None):
    thread_parser = argparse.ArgumentParser(add_help=False)
    thread_parser.add_argument("--threads", type=int, default=2)
    thread_args, remaining = thread_parser.parse_known_args(argv)
    if thread_args.threads < 1:
        thread_parser.error("--threads must be at least 1")

    torch.set_num_threads(thread_args.threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    cfg = parse_args(remaining)
    seed_everything(cfg.seed)
    FastMaia3UCIEngine(cfg).run()


if __name__ == "__main__":
    main()
