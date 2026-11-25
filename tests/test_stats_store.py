"""测试模块，覆盖统计存储相关行为和回归场景。"""
import json

from interview_loop.storage.stats_store import load_stats, save_stats


def test_save_and_load_stats(tmp_path):
    """验证保存和加载统计。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    path = tmp_path / "stats.json"
    save_stats(path, {"技术一面": {"RAG": 2}})
    loaded, error = load_stats(path, ["技术一面", "技术二面"])
    assert error is None
    assert loaded["技术一面"]["RAG"] == 2
    assert loaded["技术二面"] == {}


def test_missing_stats_returns_empty(tmp_path):
    """验证缺失统计返回空。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    loaded, error = load_stats(tmp_path / "missing.json", ["技术一面"])
    assert error is None
    assert loaded == {"技术一面": {}}


def test_corrupted_stats_returns_error(tmp_path):
    """验证损坏统计返回错误。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    path = tmp_path / "stats.json"
    path.write_text("{bad json", encoding="utf-8")
    loaded, error = load_stats(path, ["技术一面"])
    assert loaded == {"技术一面": {}}
    assert error


def test_invalid_counts_are_ignored(tmp_path):
    """验证无效计数被忽略。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({"技术一面": {"RAG": -2, "Temporal": "bad"}}), encoding="utf-8")
    loaded, error = load_stats(path, ["技术一面"])
    assert error is None
    assert loaded["技术一面"]["RAG"] == 0
    assert "Temporal" not in loaded["技术一面"]
