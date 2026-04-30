#!/usr/bin/env python3
"""Start the local Paper Radio dashboard."""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn


def _open_browser(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Paper Radio 本地控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/"
    if not args.no_open:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    print(f"Paper Radio Dashboard: {url}")
    uvicorn.run("server.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

