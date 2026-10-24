"""Record the synthetic-data demo at http://127.0.0.1:8001.

Run `uv run python -m scripts.demo` first, then:
`uv run --with playwright playwright install ffmpeg` (once), and
`uv run --with playwright python -m scripts.record_demo`
Requires a local Chromium binary and ffmpeg. No Telegram account is used.
Pass --job-id ID to reuse a previously completed real Gemma job and skip
the long CPU inference wait in the recording.
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "docs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", help="Previously completed synthetic Gemma job")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="slothsort-video-") as directory:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                record_video_dir=directory,
                record_video_size={"width": 1280, "height": 800},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            if args.job_id:
                page.route(
                    "**/api/plan-jobs",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"job_id": args.job_id}),
                    ),
                )
            video = page.video
            page.goto("http://127.0.0.1:8001", wait_until="networkidle")
            page.locator("#demo-banner").wait_for(state="visible")
            page.wait_for_timeout(1800)
            page.locator("#plan-button").click()
            page.locator("#results").wait_for(state="visible", timeout=240_000)
            page.locator("#results").scroll_into_view_if_needed()
            page.wait_for_timeout(2200)

            folder_count = page.locator(".folder-name").count()
            if folder_count == 0:
                raise RuntimeError("Gemma no propuso carpetas en esta ejecución de la demo.")
            names = ["Tecnología", "Aventura", "Cocina"]
            groups = [
                ["demo-python", "demo-web"],
                ["demo-trekking", "demo-rutas"],
                ["demo-cocina", "demo-recetas"],
            ]
            for index, (name, keys) in enumerate(zip(names, groups)):
                if index >= folder_count:
                    break
                page.locator(".folder-name").nth(index).fill(name)
                for key in keys:
                    page.locator(f'.chat-folder[data-chat-key="{key}"]').select_option(str(index))
                page.wait_for_timeout(400)
            page.screenshot(path=str(OUTPUT_DIR / "demo-poster.png"), full_page=True)
            page.wait_for_timeout(1800)
            page.locator("#apply-button").click()
            page.locator("#undo-button").wait_for(state="visible")
            page.wait_for_timeout(2200)
            page.locator("#undo-button").click()
            page.wait_for_function(
                "document.querySelector('#status').textContent.includes('carpetas revertidas')"
            )
            page.wait_for_timeout(2200)
            context.close()
            browser.close()
            source = Path(video.path())

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                "-vf", f"setpts={'PTS' if args.job_id else '0.45*PTS'},fps=30,scale=1280:-2",
                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "27",
                "-movflags", "+faststart", str(OUTPUT_DIR / "demo.mp4"),
            ],
            check=True,
        )
    print(OUTPUT_DIR / "demo.mp4")


if __name__ == "__main__":
    main()
