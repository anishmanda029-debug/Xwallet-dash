"""
run_bot.py — Start the Discord bot only
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.makedirs("bot/data", exist_ok=True)
from bot.main import main

if __name__ == "__main__":
    print("⚡ Starting XWALLET...")
    asyncio.run(main())
