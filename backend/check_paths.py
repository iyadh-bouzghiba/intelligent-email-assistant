import sys
import os
import site

print(f"--- PATH DIAGNOSTIC ---")
print(f"Executable: {sys.executable}")
print(f"Version: {sys.version}")
print(f"Library Search Paths: {sys.path}")
print(f"Site Packages: {site.getsitepackages()}")

try:
    import googleapiclient
    print("✅ googleapiclient FOUND!")
except ImportError:
    print("❌ googleapiclient MISSING!")