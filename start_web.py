#!/usr/bin/env python3

import subprocess
import webbrowser
import time
import sys
import os
import argparse
import sqlite3
from pathlib import Path

def get_cached_paths():
    """Get list of previously indexed codebase paths from cache"""
    cache_db = ".minipilot/cache.db"
    if not os.path.exists(cache_db):
        return []
    
    try:
        with sqlite3.connect(cache_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT 
                    CASE 
                        WHEN file_path LIKE '%/%' THEN 
                            substr(file_path, 1, instr(file_path, '/') - 1)
                        ELSE file_path 
                    END as root_path 
                FROM files 
                WHERE root_path != '' AND root_path IS NOT NULL
                ORDER BY root_path
            """)
            paths = [row[0] for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM files")
            file_count = cursor.fetchone()[0]
            
            if file_count > 0:
                cursor.execute("SELECT file_path FROM files LIMIT 5")
                sample_files = [row[0] for row in cursor.fetchall()]
                
                if sample_files:
                    common_prefix = os.path.commonpath([os.path.abspath(f) for f in sample_files if '/' in f])
                    if common_prefix and common_prefix not in paths:
                        paths.insert(0, common_prefix)
            
            return [p for p in paths if p and os.path.exists(p)]
    except Exception as e:
        print(f"Warning: Could not read cache: {e}")
        return []

def get_cache_stats(path=None):
    """Get cache statistics for a specific path or overall"""
    cache_db = ".minipilot/cache.db"
    if not os.path.exists(cache_db):
        return None
    
    try:
        with sqlite3.connect(cache_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM files")
            files = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunks = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            embeddings = cursor.fetchone()[0]
            
            return {
                'files': files,
                'chunks': chunks,
                'embeddings': embeddings
            }
    except Exception:
        return None

def prompt_for_path():
    """Interactively prompt user for codebase path"""
    print("\n" + "="*60)
    print("MINIPILOT - Your Local, Private Copilot")
    print("="*60)
    
    cache_stats = get_cache_stats()
    cached_paths = get_cached_paths()
    
    if cache_stats and cache_stats['files'] > 0:
        print(f"\nFound existing cache with {cache_stats['files']} files, {cache_stats['chunks']} chunks")
        
        if cached_paths:
            print("\nPreviously indexed paths:")
            for i, path in enumerate(cached_paths, 1):
                print(f"  {i}. {path}")
            
            print("\nOptions:")
            print("  [1-9] - Use a previously indexed path")
            print("  [Enter path] - Index a new codebase")
            print("  [.] - Use current directory")
            print("  [q] - Quit")
        else:
            print("\nOptions:")
            print("  [Enter path] - Specify codebase path to index")
            print("  [.] - Use current directory")
            print("  [q] - Quit")
    else:
        print("\nNo existing cache found.")
        print("\nOptions:")
        print("  [Enter path] - Specify codebase path to index")
        print("  [.] - Use current directory")
        print("  [q] - Quit")
    
    while True:
        try:
            response = input("\nEnter your choice: ").strip()
            
            if response.lower() == 'q':
                print("Goodbye!")
                sys.exit(0)
            
            if response == '.':
                return os.path.abspath('.')
            
            if response.isdigit() and cached_paths:
                choice = int(response) - 1
                if 0 <= choice < len(cached_paths):
                    return cached_paths[choice]
                else:
                    print(f"Invalid choice. Please enter 1-{len(cached_paths)} or a path.")
                    continue
            
            if response:
                path = os.path.abspath(os.path.expanduser(response))
                if os.path.exists(path):
                    return path
                else:
                    print(f"Path '{path}' does not exist. Please try again.")
                    continue
            else:
                print("Please enter a valid path or choice.")
                continue
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        except EOFError:
            print("\nGoodbye!")
            sys.exit(0)

def start_server():
    parser = argparse.ArgumentParser(description='Start Minipilot Web Server')
    parser.add_argument('codebase_path', nargs='?', 
                       help='Path to the codebase to index')
    parser.add_argument('--port', '-p', type=int, default=8000,
                       help='Port to run the web server on (default: 8000)')
    
    args = parser.parse_args()
    
    if not args.codebase_path:
        args.codebase_path = prompt_for_path()
    else:
        args.codebase_path = os.path.abspath(os.path.expanduser(args.codebase_path))
        if not os.path.exists(args.codebase_path):
            print(f"Error: Path '{args.codebase_path}' does not exist")
            sys.exit(1)
    
    print("\nStarting Minipilot...")
    
    if not os.path.exists('.env'):
        print("No .env file found. Create one with your OPENAI_API_KEY for API completions.")
    
    cmd = [sys.executable, 'web_server.py', args.codebase_path]
    if args.port != 8000:
        cmd.extend(['--port', str(args.port)])
    
    try:
        print(f"Starting web server on http://localhost:{args.port}")
        print(f"Indexing codebase: {args.codebase_path}")
        print("Server is starting up...")
        
        def wait_for_server_and_open_browser():
            try:
                import requests
                use_requests = True
            except ImportError:
                import urllib.request
                use_requests = False
            
            max_attempts = 60
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    if use_requests:
                        response = requests.get(f'http://localhost:{args.port}/api/status', timeout=2)
                        if response.status_code == 200:
                            print(f"\n Server is ready! Opening browser...")
                            time.sleep(0.5)
                            webbrowser.open(f'http://localhost:{args.port}')
                            return
                    else:
                        urllib.request.urlopen(f'http://localhost:{args.port}/api/status', timeout=2)
                        print(f"\n Server is ready! Opening browser...")
                        time.sleep(0.5)
                        webbrowser.open(f'http://localhost:{args.port}')
                        return
                except:
                    pass
                
                time.sleep(1)
                attempt += 1
                
                if attempt % 10 == 0:
                    print(f" Still waiting for server to be ready... ({attempt}s)")
            
            print(f" Server took too long to start. You can manually open http://localhost:{args.port}")
        
        import threading
        threading.Thread(target=wait_for_server_and_open_browser, daemon=True).start()
        
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == '__main__':
    start_server()