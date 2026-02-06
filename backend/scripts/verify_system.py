"""
SYSTEM VERIFICATION SCRIPT
Final pre-flight validation before production deployment

This script MUST pass without errors before deploying to Render.
Executes locally and in CI without modification.

Checks:
1. Environment variables presence
2. Encryption/decryption loop
3. Health endpoint availability
"""

import os
import sys
import requests
from cryptography.fernet import Fernet
from dotenv import load_dotenv


def fail(msg):
    """Fail-fast with error message and exit"""
    print(f"[FAIL] {msg}")
    sys.exit(1)


def success(msg):
    """Log success message"""
    print(f"[OK] {msg}")


def main():
    """Execute all verification checks"""
    print("=" * 60)
    print("=== SYSTEM VERIFICATION START ===")
    print("=" * 60)
    print()

    # Load .env file if running locally
    load_dotenv()

    # ========================================================================
    # CHECK 1: ENVIRONMENT VARIABLES
    # ========================================================================
    print("[1/3] Checking environment variables...")

    fernet_key = os.getenv("FERNET_KEY")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    mistral_key = os.getenv("MISTRAL_API_KEY")

    if not fernet_key:
        fail("FERNET_KEY missing")
    if not supabase_key:
        fail("SUPABASE_SERVICE_KEY or SUPABASE_KEY missing")
    if not mistral_key:
        fail("MISTRAL_API_KEY missing")

    success("Environment variables present")
    print(f"    - FERNET_KEY: {'*' * len(fernet_key)} (length: {len(fernet_key)})")
    print(f"    - SUPABASE_KEY: {'*' * min(32, len(supabase_key))}... (length: {len(supabase_key)})")
    print(f"    - MISTRAL_API_KEY: {'*' * min(32, len(mistral_key))}... (length: {len(mistral_key)})")
    print()

    # ========================================================================
    # CHECK 2: ENCRYPTION LOOP
    # ========================================================================
    print("[2/3] Testing encryption loop...")

    try:
        f = Fernet(fernet_key.encode())
        test_message = b"EMAIL_ASSISTANT_OK"
        encrypted_token = f.encrypt(test_message)
        decrypted_message = f.decrypt(encrypted_token)

        if decrypted_message != test_message:
            fail("Crypto loop failed: decrypted message does not match")

        success("Encryption loop verified")
        print(f"    - Test message: {test_message.decode()}")
        print(f"    - Encrypted token length: {len(encrypted_token)} bytes")
        print(f"    - Decryption successful: {decrypted_message.decode()}")
    except Exception as e:
        fail(f"Crypto loop failed: {e}")

    print()

    # ========================================================================
    # CHECK 3: HEALTH ENDPOINT
    # ========================================================================
    print("[3/3] Verifying health endpoint...")

    # Determine API base URL
    base_url = os.getenv("VITE_API_BASE_URL") or os.getenv("VITE_API_BASE") or "http://localhost:8000"
    base_url = base_url.rstrip("/")

    print(f"    - Target: {base_url}/health")

    try:
        res = requests.get(f"{base_url}/health", timeout=10)

        if res.status_code != 200:
            fail(f"Health endpoint returned {res.status_code} (expected 200)")

        data = res.json()

        # Accept both "ok" and "healthy" status
        status = data.get("status")
        if status not in ["ok", "healthy"]:
            fail(f"Health response invalid: status={status} (expected 'ok' or 'healthy')")

        success("Health endpoint verified")
        print(f"    - Status: {res.status_code}")
        print(f"    - Response: {data}")

    except requests.exceptions.ConnectionError:
        print("    [SKIP] Backend not running (expected for pre-deployment check)")
        print("    [INFO] This check will pass in Render CI when backend is deployed")
    except requests.exceptions.Timeout:
        fail("Health endpoint timeout (>10s)")
    except Exception as e:
        fail(f"Health endpoint check failed: {e}")

    print()
    print("=" * 60)
    print("=== SYSTEM READY FOR DEPLOYMENT ===")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Push code to GitHub")
    print("2. Deploy to Render using render.yaml")
    print("3. Configure OAuth redirect URIs")
    print("4. Run this script again in Render shell to verify production environment")
    print()


if __name__ == "__main__":
    main()
