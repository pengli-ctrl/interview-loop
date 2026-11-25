"""RAG 评估脚本模块，负责运行检索黄金集门禁。"""
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
    """命令行入口：运行 RAG 检索评估门禁。

    Raises:
        SystemExit: 当输入、状态或外部依赖不满足要求时抛出 SystemExit。

    """
    dataset = json.loads((ROOT / "datasets" / "rag_golden.json").read_text(encoding="utf-8"))
    documents = dataset["documents"]
    retriever = BM25Retriever.from_texts(
        [item["text"] for item in documents],
        metadatas=[{"id": item["id"]} for item in documents],
        preprocess_func=jieba.lcut,
    )
    retriever.k = int(dataset.get("k", 3))

    def search(query: str, k: int) -> list[str]:
        """在 BM25 索引中检索。

        Args:
            query: `query` 输入参数，类型为 str。
            k: `k` 输入参数，类型为 int。

        Returns:
            函数处理结果，类型为 list[str]。

        """
        retriever.k = k
        return [doc.metadata["id"] for doc in retriever.invoke(query)]

    cases = [
        RetrievalCase(query=item["query"], relevant_ids=item["relevant_ids"])
        for item in dataset["cases"]
    ]
    report = evaluate_retrieval(search, cases, k=int(dataset.get("k", 3)))
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    thresholds = dataset.get("thresholds", {})
    failed = [
        name
        for name, minimum in thresholds.items()
        if float(getattr(report, name)) < float(minimum)
    ]
    if failed:
        print(f"Retrieval thresholds failed: {', '.join(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
