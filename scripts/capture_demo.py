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

DEMO_ANSWER = (
    "我先说明业务背景和目标：这个企业知识库助手服务于 8 个业务团队，目标是降低知识检索时间，"
    "同时保证回答可追溯。团队共 6 人，我负责服务端架构、检索链路、模型网关和上线治理。"
    "方案上采用 FastAPI 分层服务，PostgreSQL 保存元数据，检索使用 BM25 与向量混合召回，"
    "模型网关负责路由、重试、熔断和成本预算。最大的难点是长尾问题召回和模型成本波动，"
    "我们通过查询改写、召回融合、缓存和 Trace 评测逐步优化，最终平均延迟下降 30%，"
    "高频问题命中率提升 22%，月度模型成本下降 18%。"
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


def wait_for_app(page: Page, text: str | None = None, timeout: int = 20000) -> None:
    page.locator('[data-testid="stAppViewContainer"]').wait_for(timeout=timeout)
    if text:
        page.get_by_text(text, exact=True).first.wait_for(timeout=timeout)
    page.wait_for_timeout(1200)


def capture(page: Page, name: str, frames: list[Path]) -> None:
    SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    FRAME_ROOT.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(600)
    page.screenshot(path=str(SCREENSHOT_ROOT / f"{name}.png"), full_page=True)
    frame_path = FRAME_ROOT / f"{name}.png"
    page.screenshot(path=str(frame_path), full_page=False)
    frames.append(frame_path)
    print(f"captured {name}")


def click_button(page: Page, name: str, timeout: int = 20000) -> None:
    button = page.get_by_role("button", name=name, exact=True).first
    button.wait_for(timeout=timeout)
    button.click()
    page.wait_for_timeout(1000)


def capture_candidate_flow(page: Page, frames: list[Path]) -> None:
    page.goto(os.environ["CAPTURE_BASE_URL"], wait_until="domcontentloaded")
    wait_for_app(page, "开始一次面试", timeout=30000)
    capture(page, "dashboard", frames)

    click_button(page, "开始一次面试")
    wait_for_app(page, "下一步：补充简历")
    capture(page, "setup", frames)

    click_button(page, "下一步：补充简历")
    wait_for_app(page, "下一步：确认并开始")
    jd = (ASSET_ROOT / "demo_jd.txt").read_text(encoding="utf-8").strip()
    page.locator("textarea").first.fill(jd)
    page.locator('input[type="file"]').set_input_files(str(ASSET_ROOT / "demo_resume.txt"))
    page.get_by_text(re.compile(r"已加载：\s*demo_resume\.txt")).wait_for(timeout=60000)
    page.wait_for_timeout(1200)
    capture(page, "setup-context", frames)

    click_button(page, "下一步：确认并开始")
    wait_for_app(page, "开始面试计时")
    checkbox = page.get_by_role("checkbox")
    checkbox.evaluate("(element) => element.click()")
    page.wait_for_timeout(800)
    capture(page, "setup-confirm", frames)

    click_button(page, "开始面试计时")
    wait_for_app(page, "回答方式", timeout=40000)
    capture(page, "interview", frames)

    page.get_by_text("文字输入", exact=True).click()
    page.get_by_text("输入文字回答", exact=True).wait_for(timeout=10000)
    page.locator("textarea").first.fill(DEMO_ANSWER)
    page.wait_for_timeout(500)
    capture(page, "interview-answer", frames)

    click_button(page, "提交回答")
    page.get_by_text(re.compile(r"阶段\s*2/6")).wait_for(timeout=30000)
    page.get_by_role("button", name="结束面试并生成复盘", exact=True).wait_for(timeout=30000)
    click_button(page, "结束面试并生成复盘")
    wait_for_app(page, "复盘报告", timeout=40000)
    page.get_by_text("结构化评估", exact=True).wait_for(timeout=30000)
    capture(page, "report", frames)

    page.get_by_text("成长记录", exact=True).first.click()
    page.locator("h2", has_text="成长记录").wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    capture(page, "growth", frames)


def capture_admin(page: Page, frames: list[Path]) -> None:
    page.goto(os.environ["CAPTURE_ADMIN_URL"], wait_until="domcontentloaded")
    wait_for_app(page, "管理控制台", timeout=30000)
    page.get_by_text("管理控制台", exact=True).first.click()
    page.get_by_text("平台控制台", exact=True).first.wait_for(timeout=30000)
    page.wait_for_timeout(1200)
    capture(page, "admin", frames)
    page.get_by_role("tab", name="评估指标").click()
    page.wait_for_timeout(1200)
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
            candidate_process, candidate_log = start_server(args.candidate_port, False, "candidate.log")
            wait_for_server(os.environ["CAPTURE_BASE_URL"])

        with sync_playwright() as playwright:
            browser, browser_name = launch_browser(playwright, args.headed)
            print(f"using browser: {browser_name}")
            page = browser.new_page(viewport=VIEWPORT, color_scheme="light")
            frames: list[Path] = []
            capture_candidate_flow(page, frames)

            if not args.external_servers:
                admin_process, admin_log = start_server(args.admin_port, True, "admin.log")
                wait_for_server(os.environ["CAPTURE_ADMIN_URL"])
            capture_admin(page, frames)
            build_gif(frames)
    finally:
        stop_server(admin_process, admin_log)
        stop_server(candidate_process, candidate_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
