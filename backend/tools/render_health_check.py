import sys
import os
import importlib

# Add the project root (../) to PYTHONPATH to simulate running from 'backend' root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

print(f"🔍 Simulating Render Environment...")
print(f"📂 Project Root: {project_root}")
print(f"🐍 PYTHONPATH: {sys.path[0]}")

def check_requirements():
    print("\n📦 Checking Critical Dependencies...")
    required = ['fastapi', 'uvicorn', 'socketio', 'pydantic', 'dotenv']
    missing = []
    
    for package in required:
        try:
            if package == 'socketio':
                import socketio
            else:
                importlib.import_module(package)
            print(f"   ✅ {package} found")
        except ImportError:
            print(f"   ❌ {package} MISSING")
            missing.append(package)
            
    return len(missing) == 0

def check_app_import():
    print("\n🚀 Attempting to import Application Entry Point...")
    try:
        from src.api.service import app
        print("   ✅ Import 'src.api.service:app' SUCCESSFUL")
        return True
    except Exception as e:
        print(f"   ❌ Import FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*50)
    print("RENDER HEALTH CHECK SIMULATOR")
    print("="*50)
    
    deps_ok = check_requirements()
    if not deps_ok:
        print("\n⛔ CRITICAL: Missing dependencies. Check requirements.txt")
        sys.exit(1)
        
    app_ok = check_app_import()
    if not app_ok:
        print("\n⛔ CRITICAL: Application failed to initialize.")
        sys.exit(1)
        
    print("\n" + "="*50)
    print("✅ HEALTH CHECK PASSED")
    print("The application structure is correct for the Start Command:")
    print("uvicorn src.api.service:app --host 0.0.0.0 --port $PORT")
    print("="*50)

if __name__ == "__main__":
    main()
