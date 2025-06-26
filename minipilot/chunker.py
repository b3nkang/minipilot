
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set
import tiktoken
import fnmatch


class FileChunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, root_path: Optional[Path] = None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.root_path = root_path
        self.gitignore_patterns = self._load_gitignore_patterns() if root_path else set()
        
        self.code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
            '.clj', '.hs', '.ml', '.elm', '.dart', '.r', '.m', '.mm',
            '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
            '.html', '.htm', '.xml', '.css', '.scss', '.sass', '.less',
            '.astro', '.vue', '.svelte', '.mjs', '.cjs',
            '.sql', '.yaml', '.yml', '.json', '.toml', '.ini', '.cfg',
            '.md', '.rst', '.txt', '.tex', '.org'
        }
    
    def should_include_file(self, file_path: Path) -> bool:
        if file_path.suffix.lower() not in self.code_extensions:
            return False
        
        skip_files = {
            'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'composer.lock',
            'Cargo.lock', 'poetry.lock', 'Pipfile.lock', 'go.sum'
        }
        
        if file_path.name in skip_files:
            return False
        
        if any(part.startswith('.') for part in file_path.parts):
            allowed_hidden = {'.gitignore', '.env.example', '.editorconfig', '.nvmrc'}
            if file_path.name not in allowed_hidden:
                return False
        
        ignore_dirs = {
            'node_modules', '__pycache__', '.git', 'build', 'dist',
            '.venv', 'venv', '.env', 'target', '.gradle', '.idea',
            '.vscode', '.vs', 'bin', 'obj', 'logs', 'tmp', 'temp',
            'coverage', '.nyc_output', '.pytest_cache', '__tests__',
            'test-results', 'dist-ssr', '.astro'
        }
        
        if any(part in ignore_dirs for part in file_path.parts):
            return False
        
        try:
            if file_path.stat().st_size > 1024 * 1024:
                return False
        except (OSError, FileNotFoundError):
            return False
        
        if self.root_path and self._is_gitignored(file_path):
            return False
        
        return True
    
    def load_file_content(self, file_path: Path) -> Optional[str]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except (UnicodeDecodeError, PermissionError, FileNotFoundError):
            return None
    
    def chunk_text(self, text: str, file_path: str) -> List[Dict]:
        tokens = self.encoding.encode(text)
        chunks = []
        
        start = 0
        chunk_id = 0
        
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            
            if start > 0:
                text_before = self.encoding.decode(tokens[:start])
                lines_before = text_before.count('\n')
            else:
                lines_before = 0
            lines_in_chunk = chunk_text.count('\n')
            
            chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
            
            chunk_data = {
                'id': f"{file_path}:{lines_before}-{lines_before + lines_in_chunk}",
                'file_path': file_path,
                'content': chunk_text,
                'hash': chunk_hash,
                'start_line': lines_before,
                'end_line': lines_before + lines_in_chunk,
                'chunk_index': chunk_id,
                'token_count': len(chunk_tokens)
            }
            
            chunks.append(chunk_data)
            chunk_id += 1
            
            if end >= len(tokens):
                break
            
            start = end - self.chunk_overlap
        
        return chunks
    
    def load_and_chunk_directory(self, directory: Path) -> List[Dict]:
        all_chunks = []
        
        for file_path in directory.rglob('*'):
            if not file_path.is_file() or not self.should_include_file(file_path):
                continue
            
            content = self.load_file_content(file_path)
            if content is None:
                continue
            
            chunks = self.chunk_text(content, str(file_path))
            all_chunks.extend(chunks)
        
        return all_chunks
    
    def get_file_hash(self, file_path: Path) -> str:
        content = self.load_file_content(file_path)
        if content is None:
            return ""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _load_gitignore_patterns(self) -> Set[str]:
        patterns = set()
        if not self.root_path:
            return patterns
        
        gitignore_path = self.root_path / '.gitignore'
        if not gitignore_path.exists():
            return patterns
        
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.add(line)
        except (UnicodeDecodeError, PermissionError, FileNotFoundError):
            pass
        
        return patterns
    
    def _is_gitignored(self, file_path: Path) -> bool:
        if not self.gitignore_patterns or not self.root_path:
            return False
        
        try:
            relative_path = file_path.relative_to(self.root_path)
            relative_str = str(relative_path)
            
            for pattern in self.gitignore_patterns:
                if pattern.endswith('/'):
                    dir_pattern = pattern.rstrip('/')
                    if any(fnmatch.fnmatch(part, dir_pattern) for part in relative_path.parts):
                        return True
                else:
                    if fnmatch.fnmatch(relative_str, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                        return True
        except ValueError:
            pass
        
        return False