#!/usr/bin/env python3

import os
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from minipilot.completion import CompletionEngine, CompletionRequest
from minipilot.indexer import CodebaseIndexer

app = Flask(__name__)
CORS(app)

codebase_path = os.path.expanduser("~/repos/fsab/fullstackatbrown.com/")
cache_dir = ".minipilot"

if not os.path.exists(codebase_path):
    codebase_path = "."

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
        
        # init fresh engine for each request
        engine = CompletionEngine(cache_dir=cache_dir, dry_run=False)
        
        request_obj = CompletionRequest(
            query=query,
            max_tokens=data.get('max_tokens', 800),
            temperature=data.get('temperature', 0.1),
            model=data.get('model', 'gpt-4o')
        )
        
        response = engine.complete(request_obj)
        
        return jsonify({
            'completion': response.completion,
            'context_length': response.context_length,
            'chunks_used': response.chunks_used,
            'search_time_ms': response.search_time_ms,
            'completion_time_ms': response.completion_time_ms
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search():
    try:
        data = request.json
        query = data.get('query', '')
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        engine = CompletionEngine(cache_dir=cache_dir, dry_run=True)
        response = engine.query_engine.search(query, max_results=10)
        
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
        indexer = CodebaseIndexer(root_path=codebase_path, cache_dir=cache_dir)
        cache_stats = indexer.cache.get_cache_stats()
        
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
        .completion h1, .completion h2, .completion h3 { color: #569cd6; margin: 15px 0 10px 0; }
        .completion strong { color: #dcdcaa; }
        .completion em { color: #ce9178; font-style: italic; }
        .completion ol, .completion ul { margin: 10px 0; padding-left: 20px; }
        .completion li { margin: 5px 0; }
        .completion p { margin: 10px 0; line-height: 1.6; }
        .completion code { background: #3c3c3c; color: #f8f8f2; padding: 2px 6px; border-radius: 3px; font-family: 'Consolas', monospace; font-size: 12px; }
        .stats { margin-top: 10px; font-size: 14px; color: #808080; }
        .search-result { background: #2d2d30; padding: 10px; margin: 5px 0; border-radius: 4px; border-left: 3px solid #569cd6; }
        .file-path { color: #569cd6; font-weight: bold; }
        .similarity { color: #4ec9b0; }
        .loading { color: #ffcc02; }
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
        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 8px; font-family: 'Menlo',  'Monaco', 'Liberation Mono', 'Courier New', monospace;">
            <h1 style="margin-bottom: 0px;">minipilot</h1>
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
            
            // Numbered lists
            html = html.replace(/^(\\d+\\. .+)$/gm, '<li>$1</li>');
            html = html.replace(/((<li>\\d+\\. .+<\\/li>\\s*)+)/g, '<ol>$1</ol>');
            html = html.replace(/<li>\\d+\\. (.+)<\\/li>/g, '<li>$1</li>');
            
            // Bullet points
            html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
            html = html.replace(/^\\* (.+)$/gm, '<li>$1</li>');
            html = html.replace(/((<li>.+<\\/li>\\s*)+)/g, '<ul>$1</ul>');
            
            // Inline code
            html = html.replace(/`(.+?)`/g, '<code>$1</code>');
            
            // Line breaks
            html = html.replace(/\\n\\n/g, '</p><p>');
            html = html.replace(/\\n/g, '<br>');
            
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
            responseContent.innerHTML = '<div class="loading">Searching...</div>';
            
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
            responseContent.innerHTML = '<div class="loading">Generating completion...</div>';
            
            const result = await makeRequest('complete', { query });
            
            if (result.error) {
                responseContent.innerHTML = `<div class="error">Error: ${escapeHtml(result.error)}</div>`;
                return;
            }
            
            const statsHtml = `
                <div class="stats">
                    Completion generated in ${result.completion_time_ms.toFixed(1)}ms | 
                    Search: ${result.search_time_ms.toFixed(1)}ms | 
                    Chunks: ${result.chunks_used} | 
                    Context: ${result.context_length} chars
                </div>
            `;
            
            const formattedCompletion = formatCompletion(result.completion);
            
            responseContent.innerHTML = statsHtml + formattedCompletion;
        }

        async function checkStatus() {
            const responseDiv = document.getElementById('response');
            const responseContent = document.getElementById('responseContent');
            
            responseDiv.style.display = 'block';
            responseContent.innerHTML = '<div class="loading">Checking status...</div>';
            
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
    print("Starting Minipilot Web Server...")
    print(f"Codebase path: {codebase_path}")
    print("Open http://localhost:8000 in your browser")
    app.run(debug=False, host='0.0.0.0', port=8000)