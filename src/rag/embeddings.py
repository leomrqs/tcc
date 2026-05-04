"""
Módulo de embeddings semânticos.

Encapsula o sentence-transformers para gerar vetores de texto.
Usa all-MiniLM-L6-v2 por padrão (384 dimensões, rápido, boa qualidade).
"""

from sentence_transformers import SentenceTransformer

from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "all-MiniLM-L6-v2"


class EmbeddingModel:
    """
    Wrapper do sentence-transformers para gerar embeddings.

    Uso:
        model = EmbeddingModel()
        vectors = model.encode(["texto 1", "texto 2"])
        query_vec = model.encode_query("busca semântica")
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or DEFAULT_MODEL
        logger.info(f"Carregando modelo de embeddings: {self.model_name}...")
        try:
            self.model = SentenceTransformer(self.model_name, local_files_only=True)
        except Exception:
            self.model = SentenceTransformer(self.model_name)
        get_dim = getattr(
            self.model, "get_embedding_dimension",
            getattr(self.model, "get_sentence_embedding_dimension", None)
        )
        self.dimension = get_dim()
        logger.info(f"  Modelo carregado ({self.dimension} dimensões)")

    def encode(self, texts: list[str], batch_size: int = 64, show_progress: bool = True) -> list[list[float]]:
        """
        Gera embeddings para uma lista de textos.

        Args:
            texts: lista de strings
            batch_size: tamanho do batch para encoding
            show_progress: mostrar barra de progresso

        Returns:
            Lista de vetores (list[float]).
        """
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def encode_query(self, query: str) -> list[float]:
        """Gera embedding para uma única query (com cache simples)."""
        if not hasattr(self, "_query_cache"):
            self._query_cache: dict[str, list[float]] = {}
        if query not in self._query_cache:
            self._query_cache[query] = self.model.encode(query, convert_to_numpy=True).tolist()
            if len(self._query_cache) > 500:
                self._query_cache.pop(next(iter(self._query_cache)))
        return self._query_cache[query]
