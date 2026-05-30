"""
Logger simples e padronizado para o projeto.
"""

import logging
import sys


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Cria e retorna um logger configurado."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level)
        # Força UTF-8 no stdout para não quebrar com acentos/símbolos no
        # console do Windows (cp1252 não codifica → ✓ • etc.).
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
