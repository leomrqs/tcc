"""
Wrapper do ChromaDB para indexação e busca vetorial.

Encapsula a criação da coleção, inserção de documentos
e busca semântica, com persistência local em disco.
"""

import shutil
from pathlib import Path

import chromadb
from chromadb.config import Settings

from src.utils.logger import get_logger
from src import config

logger = get_logger(__name__)

# Diretório de persistência do ChromaDB
CHROMA_DIR = config.DATA_DIR / "rag" / "chromadb"
COLLECTION_NAME = "knowledge_base"


class VectorStore:
    """
    Interface com o ChromaDB para a base de conhecimento RAG.

    Uso:
        store = VectorStore()
        store.add_documents(docs, embeddings)
        results = store.search(query_embedding, top_k=5)
    """

    def __init__(self, persist_dir: Path = None, collection_name: str = None):
        self.persist_dir = str(persist_dir or CHROMA_DIR)
        self.collection_name = collection_name or COLLECTION_NAME

        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},  # Distância cosseno
        )
        try:
            count = self.collection.count()
        except Exception:
            logger.warning("Índice ChromaDB corrompido — recriando banco de dados...")
            del self.client
            shutil.rmtree(self.persist_dir, ignore_errors=True)
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            count = 0
        logger.info(
            f"ChromaDB inicializado em {self.persist_dir} "
            f"(coleção '{self.collection_name}', "
            f"{count} documentos existentes)"
        )

    def add_documents(
        self,
        documents: list[dict],
        embeddings: list[list[float]],
        batch_size: int = 500,
    ) -> int:
        """
        Insere documentos e seus embeddings no ChromaDB.

        Args:
            documents: lista de dicts com keys: id, title, text, metadata, source
            embeddings: lista de vetores (mesma ordem dos documents)
            batch_size: tamanho do lote para inserção

        Returns:
            Número de documentos inseridos.
        """
        if len(documents) != len(embeddings):
            raise ValueError(
                f"documents ({len(documents)}) e embeddings ({len(embeddings)}) "
                f"devem ter o mesmo tamanho"
            )

        # Preparar dados para o ChromaDB
        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = []
        for doc in documents:
            meta = {
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
            }
            # ChromaDB aceita só str, int, float, bool em metadata
            for k, v in doc.get("metadata", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                elif isinstance(v, list):
                    meta[k] = ", ".join(str(x) for x in v)
            metadatas.append(meta)

        # Inserir em lotes
        inserted = 0
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_texts = texts[i : i + batch_size]
            batch_embeds = embeddings[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]

            self.collection.upsert(
                ids=batch_ids,
                documents=batch_texts,
                embeddings=batch_embeds,
                metadatas=batch_metas,
            )
            inserted += len(batch_ids)

            if inserted % 1000 == 0 or inserted == len(ids):
                logger.info(f"  Inseridos {inserted}/{len(ids)} documentos")

        return inserted

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict = None,
    ) -> list[dict]:
        """
        Busca os top_k documentos mais similares ao query_embedding.

        Args:
            query_embedding: vetor da query
            top_k: número de resultados
            where: filtro opcional de metadata (ex: {"source": "mitre_attack"})

        Returns:
            Lista de dicts com: id, text, metadata, distance
        """
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        docs = []
        for i in range(len(results["ids"][0])):
            docs.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

        return docs

    def count(self) -> int:
        """Retorna o número total de documentos na coleção."""
        return self.collection.count()

    def reset(self):
        """Remove todos os documentos da coleção."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Coleção resetada.")
