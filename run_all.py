"""
XWALLET run_all.py — Railway Edition
Starts: Discord Bot + Dashboard + Watcher in one process.
"""
import sys, os, asyncio, time, signal, multiprocessing, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BANNER = """
╔══════════════════════════════════════════════════╗
║          ⚡ XWALLET — Railway Edition            ║
║   Discord Bot  +  Dashboard  +  Watcher          ║
╚══════════════════════════════════════════════════╝
"""


def run_bot():
    from dotenv import load_dotenv; load_dotenv()
    import asyncio as _a
    from bot.main import main
    print("[BOT] Starting Discord bot...")
    _a.run(main())


def run_dashboard():
    from dotenv import load_dotenv; load_dotenv()
    from dashboard.app import app
    import os as _os
    port = int(_os.getenv("PORT", 5000))
    print(f"[DASH] Starting dashboard on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def run_watcher():
    from dotenv import load_dotenv; load_dotenv()
    import asyncio as _a
    import sys as _sys, os as _os

    watcher_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "bot", "watcher")
    if watcher_dir not in _sys.path:
        _sys.path.insert(0, watcher_dir)

    print("[WATCHER] Loading bot/watcher/watcher.py ...")
    try:
        import watcher as _watcher_module
    except Exception as e:
        print(f"[WATCHER] FAILED to load watcher.py: {e}")
        import traceback; traceback.print_exc()
        return

    print("[WATCHER] watcher.py loaded OK. Starting main loop...")
    try:
        _a.run(_watcher_module.main())
    except Exception as e:
        print(f"[WATCHER] crashed: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    print(BANNER)

    procs = [
        multiprocessing.Process(target=run_bot,       name="Bot",       daemon=True),
        multiprocessing.Process(target=run_dashboard,  name="Dashboard", daemon=True),
        multiprocessing.Process(target=run_watcher,    name="Watcher",   daemon=True),
    ]

    for i, p in enumerate(procs):
        p.start()
        time.sleep(2 if i == 0 else 1)

    def handle_exit(sig, frame):
        print("\n[EXIT] Shutting down...")
        for p in procs: p.terminate()
        for p in procs: p.join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT,  handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    print("[OK] All 3 processes running. Ctrl+C to stop.\n")
    for p in procs: p.join()
