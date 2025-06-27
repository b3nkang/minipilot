
import sqlite3
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime


class LocalCache:
    def __init__(self, db_path: str = ".minipilot/cache.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    content_hash TEXT NOT NULL,
                    last_modified TIMESTAMP NOT NULL,
                    file_size INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id TEXT UNIQUE NOT NULL,
                    file_path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    token_count INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_path) REFERENCES files (file_path)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id TEXT UNIQUE NOT NULL,
                    embedding_vector TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES chunks (chunk_id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS merkle_state (
                    id INTEGER PRIMARY KEY,
                    root_hash TEXT NOT NULL,
                    tree_data TEXT NOT NULL,
                    last_sync TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunks(file_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON chunks(chunk_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_id ON embeddings(chunk_id)")
            
            conn.commit()
    
    def store_file_metadata(self, file_path: str, content_hash: str, 
                          last_modified: datetime, file_size: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO files 
                (file_path, content_hash, last_modified, file_size, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (file_path, content_hash, last_modified, file_size))
            conn.commit()
    
    def get_file_metadata(self, file_path: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path, content_hash, last_modified, file_size, 
                       created_at, updated_at
                FROM files WHERE file_path = ?
            """, (file_path,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'file_path': row[0],
                    'content_hash': row[1],
                    'last_modified': row[2],
                    'file_size': row[3],
                    'created_at': row[4],
                    'updated_at': row[5]
                }
            return None
    
    def get_all_file_hashes(self) -> Dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, content_hash FROM files")
            return dict(cursor.fetchall())
    
    def store_chunks(self, chunks: List[Dict]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for chunk in chunks:
                cursor.execute("""
                    INSERT OR REPLACE INTO chunks 
                    (chunk_id, file_path, content, chunk_hash, start_line, 
                     end_line, chunk_index, token_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    chunk['id'], chunk['file_path'], chunk['content'],
                    chunk['hash'], chunk['start_line'], chunk['end_line'],
                    chunk['chunk_index'], chunk['token_count']
                ))
            
            conn.commit()
    
    def get_chunks_by_file(self, file_path: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_id, file_path, content, chunk_hash, start_line,
                       end_line, chunk_index, token_count
                FROM chunks WHERE file_path = ?
                ORDER BY chunk_index
            """, (file_path,))
            
            chunks = []
            for row in cursor.fetchall():
                chunks.append({
                    'id': row[0],
                    'file_path': row[1],
                    'content': row[2],
                    'hash': row[3],
                    'start_line': row[4],
                    'end_line': row[5],
                    'chunk_index': row[6],
                    'token_count': row[7]
                })
            
            return chunks
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_id, file_path, content, chunk_hash, start_line,
                       end_line, chunk_index, token_count
                FROM chunks WHERE chunk_id = ?
            """, (chunk_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'file_path': row[1],
                    'content': row[2],
                    'hash': row[3],
                    'start_line': row[4],
                    'end_line': row[5],
                    'chunk_index': row[6],
                    'token_count': row[7]
                }
            return None
    
    def store_embedding(self, chunk_id: str, embedding_vector: List[float], 
                       embedding_model: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO embeddings 
                (chunk_id, embedding_vector, embedding_model)
                VALUES (?, ?, ?)
            """, (chunk_id, json.dumps(embedding_vector), embedding_model))
            conn.commit()
    
    def get_embedding(self, chunk_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_id, embedding_vector, embedding_model, created_at
                FROM embeddings WHERE chunk_id = ?
            """, (chunk_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'chunk_id': row[0],
                    'embedding_vector': json.loads(row[1]),
                    'embedding_model': row[2],
                    'created_at': row[3]
                }
            return None
    
    def store_merkle_state(self, root_hash: str, tree_data: Dict):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO merkle_state 
                (id, root_hash, tree_data, last_sync, updated_at)
                VALUES (1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (root_hash, json.dumps(tree_data)))
            conn.commit()
    
    def get_merkle_state(self) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT root_hash, tree_data, last_sync, updated_at
                FROM merkle_state WHERE id = 1
            """)
            
            row = cursor.fetchone()
            if row:
                return {
                    'root_hash': row[0],
                    'tree_data': json.loads(row[1]),
                    'last_sync': row[2],
                    'updated_at': row[3]
                }
            return None
    
    def delete_file_data(self, file_path: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT chunk_id FROM chunks WHERE file_path = ?", (file_path,))
            chunk_ids = [row[0] for row in cursor.fetchall()]
            
            for chunk_id in chunk_ids:
                cursor.execute("DELETE FROM embeddings WHERE chunk_id = ?", (chunk_id,))
            
            cursor.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            
            cursor.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
            
            conn.commit()
    
    def cleanup_orphaned_data(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM files")
            files_before = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunks_before = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            embeddings_before = cursor.fetchone()[0]
            
            print(f"🧹 Cleanup: Before - Files: {files_before}, Chunks: {chunks_before}, Embeddings: {embeddings_before}")
            
            cursor.execute("""
                DELETE FROM embeddings 
                WHERE chunk_id NOT IN (SELECT chunk_id FROM chunks)
            """)
            deleted_embeddings = cursor.rowcount
            
            cursor.execute("""
                DELETE FROM chunks 
                WHERE file_path NOT IN (SELECT file_path FROM files)
            """)
            deleted_chunks = cursor.rowcount
            
            conn.commit()
            
            cursor.execute("SELECT COUNT(*) FROM files")
            files_after = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunks_after = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            embeddings_after = cursor.fetchone()[0]
            
            print(f"🧹 Cleanup: After - Files: {files_after}, Chunks: {chunks_after}, Embeddings: {embeddings_after}")
            print(f"🧹 Cleanup: Deleted {deleted_chunks} chunks, {deleted_embeddings} embeddings")
    
    def get_cache_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM files")
            file_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            embedding_count = cursor.fetchone()[0]
            
            return {
                'files': file_count,
                'chunks': chunk_count,
                'embeddings': embedding_count
            }
    
    def clear_all_cache(self):
        """Clear all cached data from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM files")
            files_before = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunks_before = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            embeddings_before = cursor.fetchone()[0]
            
            print(f"  Clearing cache: {files_before} files, {chunks_before} chunks, {embeddings_before} embeddings")
            
            cursor.execute("DELETE FROM embeddings")
            cursor.execute("DELETE FROM chunks")
            cursor.execute("DELETE FROM files")
            cursor.execute("DELETE FROM merkle_state")
            cursor.execute("DELETE FROM indexer_metadata")
            
            conn.commit()
            
            print("  Cache cleared successfully")
    
    def get_indexed_root_path(self) -> Optional[str]:
        """Get the root path that was originally indexed by analyzing file paths"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='indexer_metadata'
            """)
            
            if cursor.fetchone():
                cursor.execute("SELECT root_path FROM indexer_metadata WHERE id = 1")
                result = cursor.fetchone()
                if result:
                    return result[0]
            
            cursor.execute("SELECT file_path FROM files LIMIT 10")
            sample_files = [row[0] for row in cursor.fetchall()]
            
            if not sample_files:
                return None
            
            absolute_files = [f for f in sample_files if f.startswith('/')]
            
            if absolute_files:
                import os
                try:
                    common_prefix = os.path.commonpath(absolute_files)
                    return common_prefix
                except:
                    pass
            
            return None
    
    def store_indexed_root_path(self, root_path: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indexer_metadata (
                    id INTEGER PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                INSERT OR REPLACE INTO indexer_metadata 
                (id, root_path, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
            """, (root_path,))
            
            conn.commit()