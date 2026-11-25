import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import jieba
from langchain_community.retrievers import BM25Retriever

from interview_loop.evaluation.retrieval import RetrievalCase, evaluate_retrieval


def main() -> None:
    dataset = json.loads((ROOT / "datasets" / "rag_golden.json").read_text(encoding="utf-8"))
    documents = dataset["documents"]
    retriever = BM25Retriever.from_texts(
        [item["text"] for item in documents],
        metadatas=[{"id": item["id"]} for item in documents],
        preprocess_func=jieba.lcut,
    )
    retriever.k = int(dataset.get("k", 3))

    def search(query: str, k: int) -> list[str]:
        retriever.k = k
        return [doc.metadata["id"] for doc in retriever.invoke(query)]

    cases = [
        RetrievalCase(query=item["query"], relevant_ids=item["relevant_ids"])
        for item in dataset["cases"]
    ]
    report = evaluate_retrieval(search, cases, k=int(dataset.get("k", 3)))
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
