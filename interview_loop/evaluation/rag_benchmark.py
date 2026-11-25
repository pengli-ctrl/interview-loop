import json
from pathlib import Path

from interview_loop.evaluation.retrieval import RetrievalCase, evaluate_retrieval

DEFAULT_RAG_DATASET = (
    Path(__file__).resolve().parents[2] / "datasets" / "rag_golden.json"
)


def load_rag_dataset(path: str | Path = DEFAULT_RAG_DATASET) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_rag_dataset(dataset: dict):
    import jieba
    from langchain_community.retrievers import BM25Retriever

    documents = dataset["documents"]
    retriever = BM25Retriever.from_texts(
        [item["text"] for item in documents],
        metadatas=[{"id": item["id"]} for item in documents],
        preprocess_func=jieba.lcut,
    )

    def search(query: str, k: int) -> list[str]:
        retriever.k = k
        return [doc.metadata["id"] for doc in retriever.invoke(query)]

    cases = [
        RetrievalCase(item["query"], item["relevant_ids"])
        for item in dataset["cases"]
    ]
    return evaluate_retrieval(search, cases, k=int(dataset.get("k", 3)))


def evaluate_default_rag() -> dict:
    dataset = load_rag_dataset()
    report = evaluate_rag_dataset(dataset)
    return {
        "k": report.k,
        "precision": report.precision,
        "recall": report.recall,
        "mrr": report.mrr,
        "hit_rate": report.hit_rate,
        "thresholds": dataset.get("thresholds", {}),
        "case_count": len(dataset.get("cases", [])),
    }
