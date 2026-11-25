import os
from pathlib import Path

import streamlit as st

from interview_loop.config import EMBEDDING_CACHE_NAME, EMBEDDING_MODEL_NAME


def has_local_embedding_model() -> bool:
    try:
        hf_home = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface"))
        model_dir = hf_home / "hub" / EMBEDDING_CACHE_NAME
        snapshots_dir = model_dir / "snapshots"
        if snapshots_dir.is_dir() and any(
            (snapshot / "modules.json").is_file()
            for snapshot in snapshots_dir.iterdir()
            if snapshot.is_dir()
        ):
            return True
        legacy_dir = Path.home() / ".cache" / "torch" / "sentence_transformers" / (
            "sentence-transformers_all-MiniLM-L6-v2"
        )
        return (legacy_dir / "modules.json").is_file()
    except OSError:
        return False


@st.cache_resource(show_spinner=False)
def get_embeddings():
    from langchain_community.embeddings import SentenceTransformerEmbeddings

    return SentenceTransformerEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"local_files_only": True},
    )


def build_rag(text: str):
    try:
        import jieba
        from langchain.retrievers import EnsembleRetriever
        from langchain_community.retrievers import BM25Retriever
        from langchain_community.vectorstores import FAISS
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise RuntimeError(f"缺少 RAG 依赖：{exc}") from exc

    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    chunks = [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
    if not chunks:
        raise ValueError("简历没有可用的文本内容")

    bm25 = BM25Retriever.from_texts(chunks, preprocess_func=jieba.lcut)
    bm25.k = 2
    if not has_local_embedding_model():
        return bm25, "BM25 本地关键词"

    try:
        embeddings = get_embeddings()
        faiss_store = FAISS.from_texts(chunks, embeddings)
        retriever = EnsembleRetriever(
            retrievers=[bm25, faiss_store.as_retriever()],
            weights=[0.5, 0.5],
        )
        return retriever, "BM25 + 本地向量"
    except Exception:
        return bm25, "BM25 本地关键词"


def query_resume(retriever, query: str) -> str:
    if retriever is None:
        return ""
    try:
        docs = retriever.invoke(query or "候选人的简历与项目经历")
        return "\n".join(doc.page_content for doc in docs)
    except Exception:
        return ""
