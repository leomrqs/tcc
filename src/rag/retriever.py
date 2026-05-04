"""
Retriever — interface de alto nível para busca na base RAG.

v2: suporta cross-encoder re-ranking opcional.

Pipeline:
1. Busca top-K (default 20) por similaridade densa (ChromaDB + embeddings)
2. Se rerank=True, re-classifica via cross-encoder e pega top-N (default 3-5)
3. Retorna documentos com 'distance' atualizada (1 - rerank_score normalizado)
"""

from src.rag.embeddings import EmbeddingModel
from src.rag.vectorstore import VectorStore
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Lazy import — cross-encoder só carrega se for usado
_RERANKER = None


def _get_reranker(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """Carrega o cross-encoder uma única vez (singleton)."""
    global _RERANKER
    if _RERANKER is None:
        from sentence_transformers import CrossEncoder
        logger.info(f"Carregando cross-encoder: {model_name}...")
        _RERANKER = CrossEncoder(model_name)
        logger.info("  Cross-encoder pronto")
    return _RERANKER


class Retriever:
    """
    Interface de busca semântica na base de conhecimento.

    Combina o modelo de embeddings com o ChromaDB e (opcionalmente)
    um cross-encoder para re-ranking.
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel = None,
        vector_store: VectorStore = None,
        use_reranker: bool = True,
        rerank_pool_size: int = 20,
    ):
        self.embedding_model = embedding_model or EmbeddingModel()
        self.vector_store = vector_store or VectorStore()
        self.use_reranker = use_reranker
        self.rerank_pool_size = rerank_pool_size

        doc_count = self.vector_store.count()
        if doc_count == 0:
            logger.warning(
                "Base vetorial vazia. Rode primeiro: python -m src.rag.pipeline"
            )
        else:
            mode = " (com cross-encoder rerank)" if use_reranker else ""
            logger.info(f"Retriever pronto ({doc_count} documentos na base){mode}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        source_filter: str = None,
    ) -> list[dict]:
        """
        Busca documentos relevantes para uma query.

        Se use_reranker=True:
        - Recupera top `rerank_pool_size` por similaridade densa
        - Re-classifica via cross-encoder
        - Retorna top `top_k` da re-classificação

        Se use_reranker=False, comportamento original (denso direto).

        Distance retornada:
        - Modo denso puro: distância coseno do ChromaDB (0=igual, 2=oposto)
        - Modo re-rank: 1 - sigmoid(score), aproximação para mesma escala (0-1)
        """
        # Etapa 1: busca densa
        pool_size = self.rerank_pool_size if self.use_reranker else top_k
        query_embedding = self.embedding_model.encode_query(query)

        where = None
        if source_filter:
            where = {"source": source_filter}

        results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=pool_size,
            where=where,
        )

        # Enriquecer com title/source
        for doc in results:
            doc["title"] = doc["metadata"].get("title", "")
            doc["source"] = doc["metadata"].get("source", "")
            doc["dense_distance"] = doc["distance"]  # preserva original

        # Etapa 2: re-ranking (se habilitado e houver candidatos)
        if self.use_reranker and len(results) > 1:
            try:
                reranker = _get_reranker()
                pairs = [(query, doc["text"]) for doc in results]
                scores = reranker.predict(pairs, show_progress_bar=False)

                # Mapear scores para 'distance' (0-1, menor = melhor)
                # Cross-encoder retorna logits — normalizar via sigmoid + invert
                import math
                for doc, score in zip(results, scores):
                    sig = 1.0 / (1.0 + math.exp(-float(score)))  # sigmoid
                    doc["rerank_score"] = float(score)
                    doc["distance"] = 1.0 - sig  # quanto menor, mais relevante

                results.sort(key=lambda d: d["distance"])
            except Exception as e:
                logger.warning(f"Re-ranking falhou ({e}) — usando ordem densa")

        return results[:top_k]

    def format_context(self, results: list[dict], max_tokens: int = 3000) -> str:
        """
        Formata os resultados de busca em um bloco de contexto
        para incluir no prompt do LLM.

        Estima ~4 chars por token para controlar o tamanho.
        """
        max_chars = max_tokens * 4
        context_parts = []
        total_chars = 0

        for i, doc in enumerate(results, 1):
            source_label = {
                "mitre_attack": "MITRE ATT&CK",
                "sigma_rules": "Sigma Rule",
                "ids_classes": "IDS Class Reference",
            }.get(doc["source"], doc["source"])

            header = f"[{source_label}] {doc['title']}"
            text = doc["text"]

            available = max_chars - total_chars - len(header) - 20
            if available <= 0:
                break
            if len(text) > available:
                text = text[:available] + "..."

            block = f"--- Reference {i} ({source_label}) ---\n{text}"
            context_parts.append(block)
            total_chars += len(block)

        return "\n\n".join(context_parts)
