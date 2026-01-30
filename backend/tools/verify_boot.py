import sys
import os

print(f"🐍 Python Path: {sys.path}")
print(f"📂 CWD: {os.getcwd()}")

try:
    print("⏳ Attempting import of backend.src.api.service...")
    from backend.src.api.service import app
    print("✅ SUCCESS: App imported successfully.")
    print(f"🚀 App Object: {app}")
except ImportError as e:
    print(f"❌ FAIL: Import Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ FAIL: Runtime Error: {e}")
    sys.exit(1)
