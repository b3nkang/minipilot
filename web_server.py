#!/usr/bin/env python3

import os
import argparse
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from minipilot.completion import CompletionEngine, CompletionRequest
from minipilot.indexer import CodebaseIndexer

app = Flask(__name__)
CORS(app)

# Global variables to be set by parse_args
codebase_path = None
cache_dir = ".minipilot"
completion_engine = None

def parse_args():
    parser = argparse.ArgumentParser(description='Minipilot - Your local, private Copilot')
    parser.add_argument('codebase_path', nargs='?', 
                       default=os.path.expanduser("~/repos/fsab/fullstackatbrown.com/"),
                       help='Path to the codebase to index (default: ~/repos/fsab/fullstackatbrown.com/)')
    parser.add_argument('--port', '-p', type=int, default=8000,
                       help='Port to run the web server on (default: 8000)')
    parser.add_argument('--cache-dir', '-c', default=".minipilot",
                       help='Directory for cache and vector database (default: .minipilot)')
    
    args = parser.parse_args()
    
    args.codebase_path = os.path.abspath(os.path.expanduser(args.codebase_path))
    
    if not os.path.exists(args.codebase_path):
        if args.codebase_path == os.path.abspath(os.path.expanduser("~/repos/fsab/fullstackatbrown.com/")):
            print(f"Default path {args.codebase_path} doesn't exist, using current directory")
            args.codebase_path = os.path.abspath(".")
        else:
            print(f"Error: Specified path '{args.codebase_path}' does not exist")
            exit(1)
    
    return args

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/complete', methods=['POST'])
def complete():
    try:
        data = request.json
        query = data.get('query', '')
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        global completion_engine
        if completion_engine is None:
            completion_engine = CompletionEngine(cache_dir=cache_dir, dry_run=False)
        
        request_obj = CompletionRequest(
            query=query,
            max_tokens=data.get('max_tokens', 800),
            temperature=data.get('temperature', 0.1),
            model=data.get('model', 'gpt-4o')
        )
        
        response = completion_engine.complete(request_obj)
        
        return jsonify({
            'completion': response.completion,
            'context_length': response.context_length,
            'chunks_used': response.chunks_used,
            'search_time_ms': response.search_time_ms,
            'completion_time_ms': response.completion_time_ms
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/complete_stream', methods=['POST'])
def complete_stream():
    try:
        data = request.json
        query = data.get('query', '')
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        def generate():
            import sys
            import json
            import time
            
            # Progress tracking list
            progress_messages = []
            
            # Custom stdout that captures print statements
            class StreamingOutput:
                def __init__(self, original_stdout):
                    self.original = original_stdout
                    
                def write(self, text):
                    # Write to original stdout (terminal)
                    self.original.write(text)
                    
                    # Also capture for streaming
                    if text and text.strip():
                        progress_messages.append(text.strip())
                        
                def flush(self):
                    self.original.flush()
            
            # Set up streaming output
            old_stdout = sys.stdout
            sys.stdout = StreamingOutput(old_stdout)
            
            try:
                yield "data: " + json.dumps({'type': 'start', 'message': 'Generating completion...'}) + "\n\n"
                
                global completion_engine
                if completion_engine is None:
                    completion_engine = CompletionEngine(cache_dir=cache_dir, dry_run=False)
                
                request_obj = CompletionRequest(
                    query=query,
                    max_tokens=data.get('max_tokens', 800),
                    temperature=data.get('temperature', 0.1),
                    model=data.get('model', 'gpt-4o')
                )
                
                # Track progress messages count
                last_message_count = 0
                
                # Periodically check for new progress messages
                import threading
                completion_result = [None]
                completion_error = [None]
                
                def run_completion():
                    try:
                        result = completion_engine.complete(request_obj)
                        completion_result[0] = result
                    except Exception as e:
                        completion_error[0] = e
                
                # Start completion in background thread
                thread = threading.Thread(target=run_completion)
                thread.start()
                
                # Stream progress while completion runs
                while thread.is_alive():
                    # Check for new progress messages
                    if len(progress_messages) > last_message_count:
                        for i in range(last_message_count, len(progress_messages)):
                            message = progress_messages[i]
                            yield "data: " + json.dumps({'type': 'progress', 'message': message}) + "\n\n"
                        last_message_count = len(progress_messages)
                    
                    time.sleep(0.1)  # Small delay to avoid busy waiting
                
                # Wait for completion to finish
                thread.join()
                
                # Send any remaining progress messages
                if len(progress_messages) > last_message_count:
                    for i in range(last_message_count, len(progress_messages)):
                        message = progress_messages[i]
                        yield "data: " + json.dumps({'type': 'progress', 'message': message}) + "\n\n"
                
                # Send final result
                if completion_error[0]:
                    yield "data: " + json.dumps({'type': 'error', 'error': str(completion_error[0])}) + "\n\n"
                elif completion_result[0]:
                    response = completion_result[0]
                    yield "data: " + json.dumps({
                        'type': 'complete', 
                        'completion': response.completion,
                        'context_length': response.context_length,
                        'chunks_used': response.chunks_used,
                        'search_time_ms': response.search_time_ms,
                        'completion_time_ms': response.completion_time_ms
                    }) + "\n\n"
                else:
                    yield "data: " + json.dumps({'type': 'error', 'error': 'Unknown completion error'}) + "\n\n"
                
            except Exception as e:
                yield "data: " + json.dumps({'type': 'error', 'error': str(e)}) + "\n\n"
            finally:
                sys.stdout = old_stdout
        
        response = app.response_class(generate(), mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search():
    try:
        data = request.json
        query = data.get('query', '')
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        global completion_engine
        if completion_engine is None:
            completion_engine = CompletionEngine(cache_dir=cache_dir, dry_run=False)
        response = completion_engine.query_engine.search(query, max_results=10)
        
        results = []
        for result in response.results:
            results.append({
                'file_path': result.file_path,
                'content': result.content[:200] + '...' if len(result.content) > 200 else result.content,
                'similarity_score': result.similarity_score,
                'start_line': result.start_line,
                'end_line': result.end_line
            })
        
        return jsonify({
            'results': results,
            'total_results': response.total_results,
            'search_time_ms': response.search_time_ms
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    try:
        from minipilot.cache import LocalCache
        cache = LocalCache(db_path=f"{cache_dir}/cache.db")
        cache_stats = cache.get_cache_stats()
        
        return jsonify({
            'codebase_path': codebase_path,
            'cache_stats': cache_stats,
            'status': 'ready'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Minipilot Web Interface</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #1e1e1e; color: #d4d4d4; }
        .container { max-width: 1200px; margin: 0 auto; }
        button { font-family: 'Menlo',  'Monaco', 'Liberation Mono', 'Courier New', monospace; }
        h1 { color: #569cd6; }
        .input-section { background: #252526; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        textarea {
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
            height: 100px;
            background: #1e1e1e;
            color: #d4d4d4;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            padding: 10px 10px 10px 13px;
            font-size: 14px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        button { background: #0e639c; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:hover { background: #1177bb; }
        .response { background: #252526; padding: 20px; border-radius: 8px; margin-top: 20px; }
        .context-preview { background: #1e1e1e; padding: 15px; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 12px; white-space: pre-wrap; border: 1px solid #3c3c3c; max-height: 500px; overflow-y: auto; }
        .completion { background: #0f1419; padding: 15px; border-radius: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; border: 1px solid #3c3c3c; margin: 10px 0; line-height: 1.5; }
        .code-block { background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; margin: 10px 0; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 13px; overflow-x: auto; }
        .code-language { background: #333; color: #569cd6; padding: 8px 12px; font-size: 11px; font-weight: bold; border-bottom: 1px solid #3c3c3c; }
        .code-block pre { margin: 0; padding: 12px; background: transparent; color: #d4d4d4; white-space: pre-wrap; line-height: 1.4; }
        .completion h1, .completion h2, .completion h3 { color: #569cd6; margin: 10px 0 5px 0; }
        .completion strong { color: #7ba3d0; }
        .completion em { color: #ce9178; font-style: italic; }
        .completion ol, .completion ul { margin: 10px 0; padding-left: 20px; }
        .completion li { margin: 2px 0; line-height: 1.4; }
        .completion p { margin: 10px 0; line-height: 1.6; }
        .completion code { background: #3c3c3c; color: #f8f8f2; padding: 2px 6px; border-radius: 3px; font-family: 'Consolas', monospace; font-size: 12px; }
        .stats { margin-top: 10px; font-size: 14px; color: #808080; }
        .search-result { background: #2d2d30; padding: 10px; margin: 5px 0; border-radius: 4px; border-left: 3px solid #569cd6; }
        .file-path { color: #569cd6; font-weight: bold; }
        .similarity { color: #4ec9b0; }
        .loading { color: #ffcc02; }
        .loading-dots::after {
            content: '';
            animation: dots 1.5s steps(4, end) infinite;
        }
        @keyframes dots {
            0% { content: ''; }
            25% { content: '.'; }
            50% { content: '..'; }
            75% { content: '...'; }
            100% { content: ''; }
        }
        .error { color: #f44747; }
        .success { color: #4ec9b0; }
        textarea:focus {
            outline: 1px solid #666;
            box-shadow: 0 0 0 2px #333;
        }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; gap: -80px; font-family: 'Menlo',  'Monaco', 'Liberation Mono', 'Courier New', monospace;">
            <div style="display: flex; align-items: center; justify-content: center; gap: 14px; margin-bottom: 0px;">
                <img src="/static/logo.svg" alt="Minipilot Logo" style="height: 48px; width: 48px; display: block;">
                <h1 style="">minipilot</h1>
            </div>
            <h3 style="margin-top: 0px; margin-bottom: 25px">your local, private copilot</h3>
        </div>
        <div class="input-section">
            <div style="font-size: 15px; margin: 0px 0px 12px 3px; font-weight: 700; font-family: 'Menlo',  'Monaco', 'Liberation Mono', 'Courier New', monospace;">what can i help with?</div>
            <textarea id="queryInput" placeholder="enter your query here..."></textarea>
            <br>
            <div style="display: flex; justify-content: start; margin: 8px 0px -4px -5px;">
                <button onclick="generateCompletion()">Generate Completion</button>
                <button onclick="searchCode()">Search Code</button>
                <button onclick="checkStatus()">Check Status</button>
            </div>
        </div>
        
        <div id="response" class="response" style="display: none;">
            <div style="font-size: 15px; margin-top: 0px; font-weight: 700; margin-bottom: 10px; font-family: 'Menlo',  'Monaco', 'Liberation Mono', 'Courier New', monospace;">response</div>
            <div id="responseContent"></div>
        </div>
    </div>

    <script>
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatCompletion(completion) {
            // Parse markdown-style code blocks
            if (completion.includes('```')) {
                return formatMarkdownCompletion(completion);
            }
            // Check if it's mostly code (simple heuristic)
            else if (completion.includes('<') || completion.includes('function') || completion.includes('const ') || completion.includes('import ')) {
                return `<div class="code-block"><pre>${escapeHtml(completion)}</pre></div>`;
            } else {
                return `<div class="completion">${escapeHtml(completion).replace(/\\n/g, '<br>')}</div>`;
            }
        }

        function parseMarkdownText(text) {
            // Simple markdown parser for common elements
            let html = escapeHtml(text);
            
            // Headers
            html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
            html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
            html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
            
            // Bold text
            html = html.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
            
            // Italic text  
            html = html.replace(/\\*(.+?)\\*/g, '<em>$1</em>');
            
            // Process lists first (before line breaks to avoid <br> inside lists)
            // Numbered lists
            html = html.replace(/^(\\d+\\.)\\s*(.+)$/gm, '<li>$2</li>');
            html = html.replace(/((<li>.+<\\/li>\\n?)+)/g, function(match) {
                // Clean up newlines inside the list and wrap with <ol>
                return '<ol>' + match.replace(/\\n/g, '') + '</ol>';
            });
            
            // Bullet points  
            html = html.replace(/^[-*]\\s*(.+)$/gm, '<li>$1</li>');
            html = html.replace(/((<li>.+<\\/li>\\n?)+)/g, function(match) {
                // Only wrap if not already wrapped in ol, and clean up newlines
                if (!match.includes('<ol>')) {
                    return '<ul>' + match.replace(/\\n/g, '') + '</ul>';
                }
                return match;
            });
            
            // Inline code
            html = html.replace(/`(.+?)`/g, '<code>$1</code>');
            
            // Line breaks (but avoid inside lists)
            html = html.replace(/\\n\\n/g, '</p><p>');
            // // Only add <br> for single line breaks that are NOT inside lists
            // html = html.replace(/\\n(?![^<]*<\\/(li|ol|ul)>)/g, '<br>');
            
            // Wrap in paragraphs
            if (html && !html.startsWith('<h') && !html.startsWith('<ol') && !html.startsWith('<ul')) {
                html = '<p>' + html + '</p>';
            }
            
            return html;
        }

        function formatMarkdownCompletion(completion) {
            let formatted = '';
            const lines = completion.split('\\n');
            let inCodeBlock = false;
            let currentCodeBlock = '';
            let currentLanguage = '';
            let regularText = '';
            
            for (let line of lines) {
                if (line.startsWith('```')) {
                    if (inCodeBlock) {
                        // End of code block
                        if (currentCodeBlock.trim()) {
                            formatted += `<div class="code-block"><div class="code-language">${currentLanguage}</div><pre>${escapeHtml(currentCodeBlock.trim())}</pre></div>`;
                        }
                        currentCodeBlock = '';
                        inCodeBlock = false;
                    } else {
                        // Start of code block
                        if (regularText.trim()) {
                            formatted += `<div class="completion">${parseMarkdownText(regularText.trim())}</div>`;
                            regularText = '';
                        }
                        currentLanguage = line.replace('```', '') || 'code';
                        inCodeBlock = true;
                    }
                } else if (inCodeBlock) {
                    currentCodeBlock += line + '\\n';
                } else {
                    regularText += line + '\\n';
                }
            }
            
            // Handle any remaining content
            if (inCodeBlock && currentCodeBlock.trim()) {
                formatted += `<div class="code-block"><div class="code-language">${currentLanguage}</div><pre>${escapeHtml(currentCodeBlock.trim())}</pre></div>`;
            }
            if (regularText.trim()) {
                formatted += `<div class="completion">${parseMarkdownText(regularText.trim())}</div>`;
            }
            
            return formatted || `<div class="completion">${escapeHtml(completion)}</div>`;
        }

        async function makeRequest(endpoint, data) {
            try {
                const response = await fetch(`/api/${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });
                return await response.json();
            } catch (error) {
                return { error: error.message };
            }
        }

        async function searchCode() {
            const query = document.getElementById('queryInput').value;
            const responseDiv = document.getElementById('response');
            const responseContent = document.getElementById('responseContent');
            
            responseDiv.style.display = 'block';
            responseContent.innerHTML = '<div class="loading">Searching<span class="loading-dots"></span></div>';
            
            const result = await makeRequest('search', { query });
            
            if (result.error) {
                responseContent.innerHTML = `<div class="error">Error: ${escapeHtml(result.error)}</div>`;
                return;
            }
            
            let html = `<div class="stats">Found ${result.total_results} results in ${result.search_time_ms.toFixed(1)}ms</div>`;
            
            result.results.forEach((item, i) => {
                html += `
                    <div class="search-result">
                        <div class="file-path">${escapeHtml(item.file_path)} (lines ${item.start_line}-${item.end_line})</div>
                        <div class="similarity">Similarity: ${item.similarity_score.toFixed(3)}</div>
                        <div class="context-preview" style="max-height: 100px;">${escapeHtml(item.content)}</div>
                    </div>
                `;
            });
            
            responseContent.innerHTML = html;
        }

        async function generateCompletion() {
            const query = document.getElementById('queryInput').value;
            const responseDiv = document.getElementById('response');
            const responseContent = document.getElementById('responseContent');
            
            responseDiv.style.display = 'block';
            responseContent.innerHTML = '<div class="loading">Generating completion<span class="loading-dots"></span></div>';
            
            try {
                // Create EventSource for streaming
                const response = await fetch('/api/complete_stream', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ query })
                });
                
                if (!response.ok) {
                    throw new Error('Failed to start streaming completion');
                }
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                let progressHtml = '<div class="loading">Generating completion<span class="loading-dots"></span></div><div class="context-preview" style="max-height: 300px; overflow-y: auto;">';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                
                                if (data.type === 'start') {
                                    progressHtml = '<div class="loading">' + escapeHtml(data.message) + '<span class="loading-dots"></span></div><div class="context-preview" style="max-height: 300px; overflow-y: auto;">';
                                } else if (data.type === 'progress') {
                                    progressHtml += escapeHtml(data.message) + '\\n';
                                    responseContent.innerHTML = progressHtml + '</div>';
                                    
                                    // Auto-scroll to bottom
                                    const preview = responseContent.querySelector('.context-preview');
                                    if (preview) {
                                        preview.scrollTop = preview.scrollHeight;
                                    }
                                } else if (data.type === 'complete') {
                                    // Final completion result
                                    const statsHtml = `
                                        <div class="stats">
                                            Completion generated in ${data.completion_time_ms.toFixed(1)}ms | 
                                            Search: ${data.search_time_ms.toFixed(1)}ms | 
                                            Chunks: ${data.chunks_used} | 
                                            Context: ${data.context_length} chars
                                        </div>
                                    `;
                                    
                                    const formattedCompletion = formatCompletion(data.completion);
                                    responseContent.innerHTML = statsHtml + formattedCompletion;
                                    return;
                                } else if (data.type === 'error') {
                                    responseContent.innerHTML = `<div class="error">Error: ${escapeHtml(data.error)}</div>`;
                                    return;
                                }
                            } catch (e) {
                                console.log('Failed to parse SSE data:', line);
                            }
                        }
                    }
                }
                
            } catch (error) {
                responseContent.innerHTML = `<div class="error">Error: ${escapeHtml(error.message)}</div>`;
            }
        }

        async function checkStatus() {
            const responseDiv = document.getElementById('response');
            const responseContent = document.getElementById('responseContent');
            
            responseDiv.style.display = 'block';
            responseContent.innerHTML = '<div class="loading">Checking status<span class="loading-dots"></span></div>';
            
            try {
                const response = await fetch('/api/status');
                const result = await response.json();
                
                if (result.error) {
                    responseContent.innerHTML = `<div class="error">Error: ${escapeHtml(result.error)}</div>`;
                    return;
                }
                
                const html = `
                    <div class="success">Status: ${result.status}</div>
                    <div class="stats">
                        <div>Codebase: ${escapeHtml(result.codebase_path)}</div>
                        <div>Files cached: ${result.cache_stats.files}</div>
                        <div>Chunks: ${result.cache_stats.chunks}</div>
                        <div>Embeddings: ${result.cache_stats.embeddings}</div>
                    </div>
                `;
                
                responseContent.innerHTML = html;
            } catch (error) {
                responseContent.innerHTML = `<div class="error">Error: ${escapeHtml(error.message)}</div>`;
            }
        }

        // Check status on load
        window.onload = () => {
            checkStatus();
            document.getElementById('queryInput').focus();
        };
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    args = parse_args()
    
    # Set global variables
    codebase_path = args.codebase_path
    cache_dir = args.cache_dir
    
    print("Starting Minipilot Web Server...")
    print(f"Codebase path: {codebase_path}")
    print(f"Cache directory: {cache_dir}")
    
    # Handle indexing
    indexer = CodebaseIndexer(root_path=codebase_path, cache_dir=cache_dir)
    cache_cleared = indexer.clear_cache_if_path_changed(show_prompt=False)
    
    cache_stats = indexer.cache.get_cache_stats()
    if cache_stats['files'] == 0:
        print("\nNo indexed files found. Starting initial indexing...")
        print(f"This may take a few minutes for large codebases...")
        indexer.full_index(show_progress=True)
        print("Initial indexing complete!")
    elif cache_cleared:
        print("\nCache was cleared. Starting fresh indexing...")
        indexer.full_index(show_progress=True)
        print("Fresh indexing complete!")
    else:
        print("Using existing cache. Starting incremental sync...")
        sync_stats = indexer.incremental_sync(show_progress=True)
        if sync_stats['changes_detected']:
            print("Incremental sync complete!")
        else:
            print("No changes detected, cache is up to date!")
    
    print("Initializing completion engine...")
    completion_engine = CompletionEngine(cache_dir=cache_dir, dry_run=False)
    print("Completion engine ready!")
    
    print(f"\nOpen http://localhost:{args.port} in your browser")
    
    app.run(debug=False, host='0.0.0.0', port=args.port)