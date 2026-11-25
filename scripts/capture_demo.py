"""Capture reproducible InterviewLoop demo screenshots and an animated GIF."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PIL import Image
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = PROJECT_ROOT / "demo"
CAPTURE_ROOT = DEMO_ROOT / ".capture"
FRAME_ROOT = CAPTURE_ROOT / "frames"
SCREENSHOT_ROOT = DEMO_ROOT / "screenshots"
ASSET_ROOT = DEMO_ROOT / "assets"
GIF_PATH = DEMO_ROOT / "interview-loop.gif"

VIEWPORT = {"width": 1440, "height": 1000}
GIF_SIZE = (1200, 833)
GIF_FRAME_MS = 1600
MIN_SCREENSHOT_BYTES = 20_000

SESSION_ONE_ANSWERS = (
    "我先介绍背景和目标。我有 6 年后端与 AI 应用平台经验，目前负责企业知识库助手的"
    "服务端架构、RAG 检索链路和模型网关。团队共 6 人，我负责技术方案、核心模块实现、"
    "上线治理和跨团队协作。这个项目服务于 8 个业务团队，目标是降低知识检索时间并保证回答可追溯。",
    "这个项目的业务目标是让 8 个业务团队共享统一知识入口。我负责服务端架构、检索、"
    "模型网关和上线治理。技术上使用 FastAPI 分层服务、PostgreSQL 元数据存储、BM25 与向量混合召回，"
    "并通过模型路由、重试、熔断和 Token 预算控制成本。最大的难点是长尾问题召回和成本波动，"
    "我们通过查询改写、召回融合、缓存和 Trace 评测逐步优化，最终延迟下降 30%，命中率提升 22%。",
    "针对刚才提到的长尾召回，我补充具体做法：先按业务域重写查询，再把 BM25 和向量结果融合排序，"
    "最后用离线黄金集评估 Recall 和 MRR。上线后增加低召回告警和失败样本回流，持续迭代同义词和切分策略。"
    "这样做的好处是每项优化都可量化，缺点是维护成本更高，所以我们把评测和配置版本化，避免随意调整。",
)

SESSION_TWO_ANSWERS = (
    "我有 6 年后端和 AI 平台经验，主要方向是 RAG、Agent 工作流和模型治理。上一份工作中，"
    "我负责一个 6 人项目的服务端架构、核心实现和稳定性治理，也负责与产品、算法和运维对齐交付节奏。",
    "我负责的项目同时面临高并发和模型成本问题。架构上把在线服务、异步任务、检索和模型网关拆成清晰模块，"
    "用幂等键处理重复请求，用熔断和降级避免 Provider 故障扩散。结果上，P95 延迟下降 25%，"
    "月度模型成本下降 18%，并通过 Trace 把问题定位时间从小时级缩短到分钟级。",
    "刚才提到的降级方案需要明确边界：优先回退同类模型，其次使用缓存答案，最后切换到确定性模板并提示用户。"
    "为了保证可恢复，我们会记录请求状态、重试次数和失败原因，同时设置租户级预算和告警。"
    "这个方案的代价是复杂度上升，所以只在关键链路启用，并通过压测和故障演练验证。",
)


def wait_for_server(url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    health_url = url.rstrip("/") + "/_stcore/health"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not become ready at {url}: {last_error}")


def start_server(port: int, admin: bool, log_name: str) -> tuple[subprocess.Popen, object]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "demo_mode": "true",
            "capture_admin": "true" if admin else "false",
            "INTERVIEWLOOP_DB_PATH": str(CAPTURE_ROOT / "interview_loop.db"),
        }
    )
    log_handle = (CAPTURE_ROOT / log_name).open("w", encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "scripts/demo_app.py",
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--client.showErrorDetails",
        "none",
    ]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return process, log_handle


def stop_server(process: subprocess.Popen | None, log_handle: object | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    if log_handle is not None:
        log_handle.close()


def launch_browser(playwright: Playwright, headed: bool) -> tuple[Browser, str]:
    errors: list[str] = []
    candidates = [
        ("chromium", {}),
        ("chrome", {"channel": "chrome"}),
        ("msedge", {"channel": "msedge"}),
    ]
    for name, kwargs in candidates:
        try:
            browser = playwright.chromium.launch(headless=not headed, **kwargs)
            return browser, name
        except Exception as exc:  # noqa: BLE001 - report all local browser options
            errors.append(f"{name}: {exc}")
    raise RuntimeError("No usable Playwright browser found:\n" + "\n".join(errors))


def wait_for_streamlit_idle(page: Page, timeout: int = 30000) -> None:
    page.wait_for_function(
        """
        () => {
          const visible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== "none" &&
              style.visibility !== "hidden" &&
              rect.width > 0 && rect.height > 0;
          };
          const app = document.querySelector('[data-testid="stAppViewContainer"]');
          if (!app) return false;
          const running = Array.from(
            document.querySelectorAll('[data-testid="stStatusWidget"]')
          ).some(visible);
          const skeletons = Array.from(
            document.querySelectorAll('[data-testid*="Skeleton"]')
          ).some(visible);
          return !running && !skeletons;
        }
        """,
        timeout=timeout,
    )
    page.wait_for_timeout(250)


def assert_clean_page(page: Page, context: str) -> None:
    visible_skeletons = page.locator('[data-testid*="Skeleton"]:visible').count()
    if visible_skeletons:
        raise AssertionError(f"{context}: {visible_skeletons} skeleton element(s) are visible")
    status_widgets = page.locator('[data-testid="stStatusWidget"]:visible').count()
    if status_widgets:
        raise AssertionError(f"{context}: Streamlit status widget is still visible")
    button_names = {name.strip() for name in page.get_by_role("button").all_inner_texts()}
    leaked = button_names & {"Deploy", "Stop", "Running"}
    if leaked:
        raise AssertionError(f"{context}: forbidden toolbar/runtime buttons: {sorted(leaked)}")
    exceptions = page.locator('[data-testid="stException"]').count()
    if exceptions:
        raise AssertionError(f"{context}: {exceptions} Streamlit exception block(s) are visible")


def wait_for_app(page: Page, text: str | None = None, timeout: int = 20000) -> None:
    page.locator('[data-testid="stAppViewContainer"]').wait_for(timeout=timeout)
    if text:
        page.get_by_text(text, exact=True).first.wait_for(timeout=timeout)
    wait_for_streamlit_idle(page, timeout=timeout)


def capture(page: Page, name: str, frames: list[Path]) -> None:
    SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    FRAME_ROOT.mkdir(parents=True, exist_ok=True)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.evaluate("window.scrollTo(0, 0)")
    wait_for_streamlit_idle(page)
    assert_clean_page(page, name)
    page.screenshot(path=str(SCREENSHOT_ROOT / f"{name}.png"), full_page=True)
    frame_path = FRAME_ROOT / f"{name}.png"
    page.screenshot(path=str(frame_path), full_page=False)
    frames.append(frame_path)
    print(f"captured {name}")


def click_button(page: Page, name: str, timeout: int = 20000) -> None:
    button = page.get_by_role("button", name=name, exact=True).first
    button.wait_for(timeout=timeout)
    button.click()
    wait_for_streamlit_idle(page, timeout=timeout)


def current_interview_question(page: Page) -> str:
    deadline = time.time() + 20
    while time.time() < deadline:
        for text in page.locator("h2").all_inner_texts():
            cleaned = text.strip()
            if cleaned and cleaned != "面试室":
                return cleaned
        page.wait_for_timeout(200)
    raise AssertionError("current interview question was not found")


def submit_text_answer(
    page: Page,
    answer: str,
    timeout: int = 30000,
    before_submit: Callable[[], None] | None = None,
) -> None:
    if page.get_by_text("输入文字回答", exact=True).count() == 0:
        text_mode = page.get_by_role("radio", name="文字输入", exact=True)
        text_mode.wait_for(timeout=10000)
        text_mode.click(force=True)
        page.get_by_text("输入文字回答", exact=True).wait_for(timeout=10000)
    previous_question = current_interview_question(page)
    textarea = page.locator("textarea").first
    textarea.fill(answer)
    if textarea.input_value().strip() != answer.strip():
        raise AssertionError("text answer was not written into the form")
    if before_submit is not None:
        before_submit()
    click_button(page, "提交回答", timeout=timeout)
    page.wait_for_function(
        """
        (previous) => Array.from(document.querySelectorAll("h2")).some((element) => {
          const text = element.innerText.trim();
          return text !== "" && text !== "面试室" && text !== previous;
        })
        """,
        arg=previous_question,
        timeout=timeout,
    )
    wait_for_streamlit_idle(page, timeout=timeout)


def begin_session(
    page: Page,
    *,
    capture_setup: bool,
    upload_resume: bool,
    frames: list[Path],
) -> None:
    if page.get_by_text("下一步：补充简历", exact=True).count() == 0:
        click_button(page, "开始一次面试")
        wait_for_app(page, "下一步：补充简历")
    if capture_setup:
        capture(page, "setup", frames)

    click_button(page, "下一步：补充简历")
    wait_for_app(page, "下一步：确认并开始")
    jd = (ASSET_ROOT / "demo_jd.txt").read_text(encoding="utf-8").strip()
    jd_input = page.locator("textarea").first
    jd_input.fill(jd)
    jd_input.evaluate("(element) => { element.scrollTop = 0; element.blur(); }")
    if upload_resume:
        page.locator('input[type="file"]').set_input_files(str(ASSET_ROOT / "demo_resume.txt"))
        page.get_by_text(re.compile(r"已加载：\s*demo_resume\.txt")).wait_for(timeout=60000)
        wait_for_streamlit_idle(page, timeout=60000)
    if capture_setup:
        page.locator("textarea").first.evaluate("(element) => { element.scrollTop = 0; }")
        capture(page, "setup-context", frames)

    click_button(page, "下一步：确认并开始")
    wait_for_app(page, "开始面试计时")
    checkbox = page.get_by_role("checkbox")
    if not checkbox.is_checked():
        checkbox.evaluate("(element) => element.click()")
    wait_for_streamlit_idle(page)
    if capture_setup:
        capture(page, "setup-confirm", frames)

    click_button(page, "开始面试计时")
    wait_for_app(page, "回答方式", timeout=40000)


def run_session(
    page: Page,
    answers: tuple[str, str, str],
    *,
    capture_setup: bool,
    upload_resume: bool,
    frames: list[Path],
) -> None:
    begin_session(
        page,
        capture_setup=capture_setup,
        upload_resume=upload_resume,
        frames=frames,
    )
    if capture_setup:
        capture(page, "interview", frames)
    before_submit = None
    if capture_setup:
        before_submit = partial(capture, page, "interview-answer", frames)
    submit_text_answer(page, answers[0], before_submit=before_submit)
    submit_text_answer(page, answers[1])
    submit_text_answer(page, answers[2])

    click_button(page, "结束面试并生成复盘")
    page.get_by_role("button", name="确认结束", exact=True).wait_for(timeout=20000)
    click_button(page, "确认结束")
    wait_for_app(page, "复盘报告", timeout=40000)
    page.get_by_text("表达结构参考分", exact=True).first.wait_for(timeout=30000)
    page.get_by_text(re.compile(r"优先行动")).first.wait_for(timeout=30000)


def capture_candidate_flow(page: Page, frames: list[Path]) -> None:
    page.goto(os.environ["CAPTURE_BASE_URL"], wait_until="domcontentloaded")
    wait_for_app(page, "开始一次面试", timeout=30000)
    capture(page, "dashboard", frames)
    run_session(
        page,
        SESSION_ONE_ANSWERS,
        capture_setup=True,
        upload_resume=True,
        frames=frames,
    )
    click_button(page, "再练一轮")
    wait_for_app(page, "下一步：补充简历")
    run_session(
        page,
        SESSION_TWO_ANSWERS,
        capture_setup=False,
        upload_resume=False,
        frames=frames,
    )
    capture(page, "report", frames)

    page.get_by_text("成长记录", exact=True).first.click()
    page.locator("h2", has_text="成长记录").wait_for(timeout=20000)
    page.get_by_text("历史面试", exact=False).first.wait_for(timeout=20000)
    wait_for_streamlit_idle(page)
    capture(page, "growth", frames)


def capture_admin(page: Page, frames: list[Path]) -> None:
    page.goto(os.environ["CAPTURE_ADMIN_URL"], wait_until="domcontentloaded")
    wait_for_app(page, "管理控制台", timeout=30000)
    page.get_by_text("管理控制台", exact=True).first.click()
    wait_for_app(page, "平台控制台", timeout=30000)
    page.get_by_text("场景目录", exact=True).wait_for(timeout=30000)
    page.locator('[data-testid="stDataFrame"]').first.wait_for(timeout=30000)
    if page.get_by_text("训练入口", exact=True).count():
        raise AssertionError("admin page still contains dashboard content")
    page.get_by_role("tab", name="AgentRun / Trace").click()
    page.get_by_text("最近 AgentRun", exact=True).first.wait_for(timeout=30000)
    if page.get_by_text("暂无 AgentRun", exact=False).count():
        raise AssertionError("admin page cannot see UI-created AgentRun records")
    capture(page, "admin", frames)

    page.get_by_role("tab", name="评估指标").click()
    page.get_by_text("RAG 检索指标", exact=True).wait_for(timeout=30000)
    wait_for_streamlit_idle(page)
    capture(page, "admin-evaluation", frames)


def build_gif(frames: list[Path]) -> None:
    if not frames:
        raise RuntimeError("No frames were captured")
    images: list[Image.Image] = []
    for path in frames:
        image = Image.open(path).convert("RGB")
        image.thumbnail(GIF_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", GIF_SIZE, "white")
        left = (GIF_SIZE[0] - image.width) // 2
        top = (GIF_SIZE[1] - image.height) // 2
        canvas.paste(image, (left, top))
        images.append(canvas.quantize(colors=192, method=Image.Quantize.MEDIANCUT))
    images[0].save(
        GIF_PATH,
        save_all=True,
        append_images=images[1:],
        duration=GIF_FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    size_mb = GIF_PATH.stat().st_size / (1024 * 1024)
    print(f"generated {GIF_PATH} ({size_mb:.2f} MB, {len(images)} frames)")


def verify_artifacts() -> None:
    sessions = sorted(
        path for path in (CAPTURE_ROOT / "sessions").glob("*.json")
        if path.name != "weak_stats.json"
    )
    records = sorted((CAPTURE_ROOT / "records").glob("*.md"))
    if len(sessions) != 2:
        raise AssertionError(f"expected 2 demo sessions, found {len(sessions)}")
    if len(records) != 2:
        raise AssertionError(f"expected 2 markdown records, found {len(records)}")
    required = [
        "dashboard.png",
        "setup.png",
        "setup-context.png",
        "setup-confirm.png",
        "interview.png",
        "interview-answer.png",
        "report.png",
        "growth.png",
        "admin.png",
        "admin-evaluation.png",
    ]
    for name in required:
        path = SCREENSHOT_ROOT / name
        if not path.is_file():
            raise AssertionError(f"missing screenshot: {path}")
        if path.stat().st_size < MIN_SCREENSHOT_BYTES:
            raise AssertionError(f"screenshot is unexpectedly small: {path}")
    with Image.open(GIF_PATH) as image:
        if image.n_frames < 10:
            raise AssertionError(f"GIF has too few frames: {image.n_frames}")
    for log_name in ("candidate.log", "admin.log"):
        log_text = (CAPTURE_ROOT / log_name).read_text(encoding="utf-8")
        if "Traceback" in log_text or "Uncaught exception" in log_text:
            raise AssertionError(f"{log_name} contains a server exception")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-port", type=int, default=8502)
    parser.add_argument("--admin-port", type=int, default=8503)
    parser.add_argument("--headed", action="store_true", help="Show the browser while capturing")
    parser.add_argument("--external-servers", action="store_true", help="Use existing servers")
    parser.add_argument("--keep-capture", action="store_true", help="Keep the isolated demo database")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.keep_capture and CAPTURE_ROOT.exists():
        shutil.rmtree(CAPTURE_ROOT)
    for directory in (CAPTURE_ROOT, FRAME_ROOT, SCREENSHOT_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    os.environ["CAPTURE_BASE_URL"] = f"http://localhost:{args.candidate_port}"
    os.environ["CAPTURE_ADMIN_URL"] = f"http://localhost:{args.admin_port}"

    candidate_process = candidate_log = admin_process = admin_log = None
    try:
        if not args.external_servers:
            candidate_process, candidate_log = start_server(
                args.candidate_port,
                False,
                "candidate.log",
            )
            wait_for_server(os.environ["CAPTURE_BASE_URL"])

        with sync_playwright() as playwright:
            browser, browser_name = launch_browser(playwright, args.headed)
            print(f"using browser: {browser_name}")
            page = browser.new_page(viewport=VIEWPORT, color_scheme="light")
            frames: list[Path] = []
            capture_candidate_flow(page, frames)
            if not args.external_servers:
                admin_process, admin_log = start_server(
                    args.admin_port,
                    True,
                    "admin.log",
                )
                wait_for_server(os.environ["CAPTURE_ADMIN_URL"])
            capture_admin(page, frames)
            build_gif(frames)
            verify_artifacts()
    finally:
        stop_server(admin_process, admin_log)
        stop_server(candidate_process, candidate_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
