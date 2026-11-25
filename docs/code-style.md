# 代码注释规范

InterviewLoop 对所有 Python 模块、类和函数执行中文 Google 风格 docstring 门禁。

## 适用范围

门禁扫描以下目录中的全部 Python 文件：

- `app.py`
- `interview_loop/`
- `scripts/`
- `tests/`

不检查缓存、虚拟环境、演示临时目录和 Git 内部目录。

## 模块注释

每个 Python 文件的第一个语句必须是模块 docstring，并说明模块作用。示例：

```python
"""面试流程模块，负责追问、主问题、阶段推进和结束决策。"""
```

模块说明必须包含中文，并明确该模块承担的职责，不能只写模块名。

## 函数与方法注释

所有函数、异步函数、方法和测试函数都必须包含中文 Google 风格 docstring。

### 无参数、无返回值

```python
def reset_state():
    """重置当前状态。"""
```

### 有参数

```python
def decide_next_step(*, main_count: int, answer: str) -> FlowDecision:
    """决定下一步面试流程。

    Args:
        main_count: 当前阶段主问题数量。
        answer: 候选人回答文本。

    Returns:
        下一步流程决策。
    """
```

### 可能抛出异常

```python
def parse_tags(raw: str) -> list[str]:
    """解析标签列表。

    Args:
        raw: 模型返回的文本。

    Returns:
        合法标签列表。

    Raises:
        ValueError: 当输入文本无法解析时抛出。
    """
```

### 生成器

包含 `yield` 的函数使用 `Yields` 章节：

```python
def iter_runs():
    """迭代运行记录。

    Yields:
        单条运行记录。
    """
```

## 类注释

每个类必须有中文 docstring，说明其职责。数据类可以在 `Attributes` 中补充关键字段：

```python
@dataclass(frozen=True)
class FlowDecision:
    """面试流程决策。

    Attributes:
        action: 下一步动作。
        main_index: 主问题索引。
        followup_count: 当前追问次数。
    """
```

## 自动检查

运行门禁：

```powershell
python scripts/check_docstrings.py
```

门禁会检查：

- 模块是否具有中文作用说明；
- 类、函数、异步函数和方法是否存在中文 docstring；
- 有参数时是否包含 `Args` 及全部参数；
- 有返回值时是否包含 `Returns`；
- 有 `yield` 时是否包含 `Yields`；
- 存在 `raise` 时是否包含 `Raises` 及异常类型。

## 自动补齐

补齐缺失注释：

```powershell
python scripts/check_docstrings.py --fix
```

统一重写自动生成的注释摘要：

```powershell
python scripts/check_docstrings.py --fix --rewrite
```

> 注意：`--rewrite` 会覆盖已有摘要，包括手工修订内容。它只适合在批量初始化时使用；日常提交只需运行不带参数的检查。批量重写后必须逐文件人工复核，并重新运行 Ruff 和测试。

## 推送门禁

仓库使用 `.githooks/pre-push`：

```sh
python scripts/check_docstrings.py
ruff check .
pytest -q
```

启用方式：

```powershell
git config core.hooksPath .githooks
```

GitHub Actions 也会在测试任务中执行 `python scripts/check_docstrings.py`，即使本地未启用 hook，CI 仍会拦截不合格注释。
