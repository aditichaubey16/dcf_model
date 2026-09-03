"""Entry point: run this to start the PE DCF Analyzer locally.

    python app.py

Opens http://127.0.0.1:8010 in your default browser. Runs entirely on this
machine — no external services are contacted.
"""
import threading
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8030


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    threading.Timer(1.25, _open_browser).start()
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=False)
