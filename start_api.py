#!/usr/bin/env python3
"""
Start MovieLinkBD API Server
"""

import subprocess
import sys
import os

def start_server():
    """Start the MovieLinkBD API server"""
    print("🚀 Starting MovieLinkBD API Server...")
    print("=" * 50)
    
    # Check if virtual environment exists
    if not os.path.exists('venv'):
        print("❌ Virtual environment not found. Please run the scraper first to create it.")
        return
    
    # Activate virtual environment and start server
    if sys.platform == "win32":
        activate_cmd = "venv\\Scripts\\activate"
        python_cmd = "venv\\Scripts\\python"
    else:
        activate_cmd = "source venv/bin/activate"
        python_cmd = "venv/bin/python"
    
    try:
        # Start the Flask server
        subprocess.run([python_cmd, "movielinkbd_api.py"], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    start_server()
