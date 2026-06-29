"""
run_dashboard.py — Start the Flask dashboard only
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.makedirs("bot/data", exist_ok=True)
from dashboard.app import app

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG","false").lower() == "true"
    print(f"🌐 Starting Dashboard on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=debug)
