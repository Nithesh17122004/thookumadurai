"""
Thooku Madurai — Combined Dev Server Launcher
Serves frontend on port 5500 from the /frontend folder
Serves backend (Flask) on port 5000
"""
import subprocess
import sys
import os
import webbrowser
import time
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, "frontend")
BACKEND_DIR  = os.path.join(ROOT, "backend")

def start_frontend():
    print("[FRONTEND] Starting at http://127.0.0.1:5500/")
    os.chdir(FRONTEND_DIR)
    subprocess.run([sys.executable, "-m", "http.server", "5500", "--bind", "127.0.0.1"])

def start_backend():
    print("[BACKEND]  Starting at http://127.0.0.1:5000/")
    os.chdir(BACKEND_DIR)
    subprocess.run([sys.executable, "app.py"])

if __name__ == "__main__":
    print("=" * 50)
    print("   THOOKU MADURAI — DEV SERVER")
    print("=" * 50)
    print(f"  Frontend : http://127.0.0.1:5500/")
    print(f"  Login    : http://127.0.0.1:5500/login.html")
    print(f"  Backend  : http://127.0.0.1:5000/health")
    print("=" * 50)

    t1 = threading.Thread(target=start_backend,  daemon=True)
    t2 = threading.Thread(target=start_frontend, daemon=True)
    t1.start()
    time.sleep(2)
    t2.start()

    time.sleep(3)
    webbrowser.open("http://127.0.0.1:5500/login.html")
    print("\n[OK] Browser opened. Press Ctrl+C to stop.\n")

    try:
        t1.join()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
