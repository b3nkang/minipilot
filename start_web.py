#!/usr/bin/env python3

import subprocess
import webbrowser
import time
import sys
import os

def start_server():
    print("Starting Minipilot...")
    
    if not os.path.exists('.env'):
        print("No .env file found. Create one with your OPENAI_API_KEY for API completions.")
    
    try:
        print("Starting web server on http://localhost:8000")
        print("Opening browser...")
        
        def open_browser():
            time.sleep(1.5)
            webbrowser.open('http://localhost:8000')
        
        import threading
        threading.Thread(target=open_browser).start()
        
        subprocess.run([sys.executable, 'web_server.py'])
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == '__main__':
    start_server()