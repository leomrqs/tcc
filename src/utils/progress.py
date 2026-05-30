"""
Acompanhamento de progresso para processos longos (baterias e benchmarks).

Mantém o terminal organizado e previsível: a cada passo mostra índice, %, tempo
decorrido, tempo médio por passo e ETA. Pensado para deixar claro, a qualquer
momento, quanto falta e quanto tempo vai levar.
"""

from __future__ import annotations

import time


def format_duration(seconds: float) -> str:
    """Formata segundos como '12s', '3m 04s' ou '1h 02m'."""
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


def banner(title: str, width: int = 70, char: str = "=") -> str:
    """Banner de seção padronizado (retorna string para log/print)."""
    line = char * width
    return f"\n{line}\n{title}\n{line}"


class ProgressTracker:
    """
    Rastreia o progresso de uma sequência de passos com ETA.

        prog = ProgressTracker(total=18, label="Treino de modelos")
        for ...:
            prog.start_step("RandomForest (CIC)")
            ... trabalho ...
            print(prog.end_step())
    """

    def __init__(self, total: int, label: str = "Progresso", printer=print):
        self.total = max(1, total)
        self.label = label
        self.printer = printer
        self.done = 0
        self.t0 = time.time()
        self._step_t0 = None
        self._current = ""

    def start_step(self, name: str) -> str:
        self._step_t0 = time.time()
        self._current = name
        pct = 100 * self.done / self.total
        msg = (f"[{self.done + 1}/{self.total}] {pct:5.1f}% | "
               f"decorrido {format_duration(time.time() - self.t0)} | "
               f"ETA {self._eta()} | INICIANDO: {name}")
        self.printer(msg)
        return msg

    def end_step(self, extra: str = "") -> str:
        self.done += 1
        step_dt = time.time() - (self._step_t0 or self.t0)
        pct = 100 * self.done / self.total
        msg = (f"[{self.done}/{self.total}] {pct:5.1f}% | "
               f"{self._current} concluído em {format_duration(step_dt)} | "
               f"decorrido {format_duration(time.time() - self.t0)} | "
               f"ETA {self._eta()}")
        if extra:
            msg += f" | {extra}"
        self.printer(msg)
        return msg

    def _eta(self) -> str:
        if self.done == 0:
            return "estimando..."
        avg = (time.time() - self.t0) / self.done
        return format_duration(avg * (self.total - self.done))

    def finish(self) -> str:
        msg = (f"CONCLUÍDO: {self.done}/{self.total} passos em "
               f"{format_duration(time.time() - self.t0)} ({self.label})")
        self.printer(banner(msg))
        return msg
