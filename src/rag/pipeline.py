"""
Orquestrador do pipeline RAG.

Executa a sequência completa:
1. Baixa MITRE ATT&CK e Sigma Rules (se não existirem)
2. Parseia as fontes em documentos textuais
3. Gera embeddings via sentence-transformers
4. Indexa no ChromaDB

Uso:
    python -m src.rag.pipeline              # pipeline completo
    python -m src.rag.pipeline --reset      # limpar base e re-indexar
    python -m src.rag.pipeline --test       # rodar testes de busca após indexar
    python -m src.rag.pipeline --skip-download  # pular download (usar fontes já baixadas)
"""

import argparse
import time

from src.rag.download import download_mitre, download_sigma, MITRE_FILE, SIGMA_DIR
from src.rag.sources.mitre import parse_mitre_attack
from src.rag.sources.sigma import parse_sigma_rules
from src.rag.sources.ids_classes import parse_ids_classes
from src.rag.embeddings import EmbeddingModel
from src.rag.vectorstore import VectorStore
from src.rag.retriever import Retriever
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_pipeline(reset: bool = False, test: bool = False, skip_download: bool = False):
    """Executa o pipeline RAG completo."""
    start_time = time.time()

    # ── 1. Download das fontes ──
    if not skip_download:
        logger.info("=" * 60)
        logger.info("ETAPA 1: DOWNLOAD DAS FONTES")
        logger.info("=" * 60)
        download_mitre()
        download_sigma()
    else:
        logger.info("Download pulado (--skip-download)")

    # ── 2. Parsing ──
    logger.info("=" * 60)
    logger.info("ETAPA 2: PARSING DAS FONTES")
    logger.info("=" * 60)

    all_documents = []

    # IDS Class descriptions (curadoria interna — alta prioridade semântica)
    ids_docs = parse_ids_classes()
    all_documents.extend(ids_docs)
    logger.info(f"  IDS Classes: {len(ids_docs)} documentos canônicos")

    # MITRE ATT&CK
    if MITRE_FILE.exists():
        mitre_docs = parse_mitre_attack(MITRE_FILE)
        all_documents.extend(mitre_docs)
        logger.info(f"  MITRE ATT&CK: {len(mitre_docs)} documentos")
    else:
        logger.warning(f"  MITRE ATT&CK não encontrado em {MITRE_FILE}")

    # Sigma Rules
    if SIGMA_DIR.exists():
        sigma_docs = parse_sigma_rules(SIGMA_DIR)
        all_documents.extend(sigma_docs)
        logger.info(f"  Sigma Rules: {len(sigma_docs)} documentos")
    else:
        logger.warning(f"  Sigma Rules não encontradas em {SIGMA_DIR}")

    if not all_documents:
        logger.error("Nenhum documento encontrado. Rode o download primeiro.")
        return

    logger.info(f"  Total: {len(all_documents)} documentos para indexar")

    # ── 3. Embeddings ──
    logger.info("=" * 60)
    logger.info("ETAPA 3: GERAÇÃO DE EMBEDDINGS")
    logger.info("=" * 60)

    embedding_model = EmbeddingModel()
    texts = [doc["text"] for doc in all_documents]
    embeddings = embedding_model.encode(texts)

    logger.info(f"  {len(embeddings)} embeddings gerados ({embedding_model.dimension} dimensões)")

    # ── 4. Indexação ──
    logger.info("=" * 60)
    logger.info("ETAPA 4: INDEXAÇÃO NO CHROMADB")
    logger.info("=" * 60)

    store = VectorStore()
    if reset:
        logger.info("  Resetando base vetorial...")
        store.reset()

    inserted = store.add_documents(all_documents, embeddings)
    logger.info(f"  {inserted} documentos indexados")
    logger.info(f"  Total na base: {store.count()}")

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"Pipeline RAG concluído em {elapsed:.1f}s")
    logger.info("=" * 60)

    # ── 5. Testes (opcional) ──
    if test:
        _run_tests(embedding_model, store)


def _run_tests(embedding_model: EmbeddingModel, store: VectorStore):
    """Roda buscas de teste para validar o RAG."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TESTES DE BUSCA")
    logger.info("=" * 60)

    retriever = Retriever(embedding_model=embedding_model, vector_store=store)

    test_queries = [
        "SSH brute force login attempts",
        "DDoS distributed denial of service attack",
        "SQL injection web application",
        "lateral movement within network",
        "port scanning reconnaissance",
        "malware command and control communication",
        "data exfiltration techniques",
        "ransomware encryption detection",
    ]

    for query in test_queries:
        logger.info(f"\nQuery: \"{query}\"")
        results = retriever.search(query, top_k=3)

        for i, doc in enumerate(results, 1):
            source = doc["metadata"].get("source", "?")
            title = doc["metadata"].get("title", "?")
            dist = doc["distance"]
            logger.info(f"  {i}. [{source}] {title} (distância: {dist:.4f})")


def main():
    parser = argparse.ArgumentParser(description="Pipeline RAG: download → parse → embed → index")
    parser.add_argument("--reset", action="store_true", help="Limpar base e re-indexar tudo")
    parser.add_argument("--test", action="store_true", help="Rodar testes de busca após indexar")
    parser.add_argument("--skip-download", action="store_true", help="Pular etapa de download")
    args = parser.parse_args()

    run_pipeline(reset=args.reset, test=args.test, skip_download=args.skip_download)


if __name__ == "__main__":
    main()
