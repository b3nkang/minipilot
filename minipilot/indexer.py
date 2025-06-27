
import os
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime
import hashlib

from .chunker import FileChunker
from .merkle_tree import FileChangeDetector
from .cache import LocalCache
from .vector_db import VectorDatabase
from .embeddings import LocalEmbeddings


class CodebaseIndexer:
    def __init__(self, 
                 root_path: str,
                 cache_dir: str = ".minipilot",
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200):
        self.root_path = Path(root_path)
        self.cache_dir = Path(cache_dir)
        
        self.chunker = FileChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap, root_path=self.root_path)
        self.merkle_detector = FileChangeDetector()
        self.cache = LocalCache(db_path=str(self.cache_dir / "cache.db"))
        self.vector_db = VectorDatabase(db_path=str(self.cache_dir / "chroma_db"))
        self.embeddings = LocalEmbeddings()
        
        self.last_sync_time = None
        self.total_files = 0
        self.processed_files = 0
    
    def get_all_file_hashes(self) -> Dict[str, str]:
        file_hashes = {}
        
        for file_path in self.root_path.rglob('*'):
            if not file_path.is_file() or not self.chunker.should_include_file(file_path):
                continue
            
            relative_path = str(file_path.relative_to(self.root_path))
            file_hash = self.chunker.get_file_hash(file_path)
            
            if file_hash:
                file_hashes[relative_path] = file_hash
        
        return file_hashes
    
    def detect_changes(self) -> Dict[str, Set[str]]:
        current_file_hashes = self.get_all_file_hashes()
        
        merkle_state = self.cache.get_merkle_state()
        if merkle_state:
            self.merkle_detector.build_tree_from_files(merkle_state['tree_data'])
        
        changes = self.merkle_detector.detect_changes(current_file_hashes)
        
        self.merkle_detector.update_tree(current_file_hashes)
        self.cache.store_merkle_state(
            self.merkle_detector.get_root_hash(),
            current_file_hashes
        )
        
        return changes
    
    def process_file(self, file_path: Path, force: bool = False) -> bool:
        relative_path = str(file_path.relative_to(self.root_path))
        
        if not force:
            cached_metadata = self.cache.get_file_metadata(relative_path)
            current_hash = self.chunker.get_file_hash(file_path)
            
            if cached_metadata and cached_metadata['content_hash'] == current_hash:
                return False
        
        print(f"Processing file: {relative_path}")
        
        content = self.chunker.load_file_content(file_path)
        if content is None:
            return False
        
        chunks = self.chunker.chunk_text(content, relative_path)
        if not chunks:
            print(f"WARNING: No chunks created for {relative_path}")
            return False
        
        print(f"  Created {len(chunks)} chunks for {relative_path}")
        
        print(f"  → Deleting old data for: {relative_path}")
        self.cache.delete_file_data(relative_path)
        self.vector_db.delete_chunks_by_file(relative_path)
        
        file_stat = file_path.stat()
        file_content_hash = hashlib.sha256(content.encode()).hexdigest()
        print(f"  → Storing file metadata for: {relative_path}")
        self.cache.store_file_metadata(
            relative_path,
            file_content_hash,
            datetime.fromtimestamp(file_stat.st_mtime),
            file_stat.st_size
        )
        
        stored_file = self.cache.get_file_metadata(relative_path)
        if stored_file:
            print(f"  →   File metadata stored successfully")
        else:
            print(f"  -> File metadata NOT stored!")
        
        print(f"  → Storing {len(chunks)} chunks in cache...")
        self.cache.store_chunks(chunks)
        
        stored_chunks = self.cache.get_chunks_by_file(relative_path)
        print(f"  → Verified: {len(stored_chunks)} chunks stored in cache")
        
        chunk_contents = [chunk['content'] for chunk in chunks]
        file_paths = [relative_path for _ in chunks]
        embeddings = self.embeddings.embed_code_chunks(chunk_contents, file_paths)
        
        vector_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            self.cache.store_embedding(
                chunk['id'], 
                embedding, 
                self.embeddings.model_name
            )
            
            vector_chunks.append({
                'chunk_id': chunk['id'],
                'content': chunk['content'],
                'embedding': embedding,
                'file_path': chunk['file_path'],
                'start_line': chunk['start_line'],
                'end_line': chunk['end_line'],
                'chunk_index': chunk['chunk_index'],
                'token_count': chunk['token_count'],
                'chunk_hash': chunk['hash']
            })
        
        self.vector_db.add_chunks(vector_chunks)
        
        return True
    
    def full_index(self, show_progress: bool = True) -> Dict:
        print("Starting full codebase indexing...")
        
        self.cache.store_indexed_root_path(str(self.root_path.resolve()))
        
        all_files = []
        for file_path in self.root_path.rglob('*'):
            if file_path.is_file() and self.chunker.should_include_file(file_path):
                all_files.append(file_path)
        
        self.total_files = len(all_files)
        self.processed_files = 0
        
        print(f"Found {self.total_files} files to index")
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        for i, file_path in enumerate(all_files):
            try:
                was_processed = self.process_file(file_path, force=True)
                if was_processed:
                    processed_count += 1
                else:
                    skipped_count += 1
                
                self.processed_files += 1
                
                if show_progress and (i + 1) % 10 == 0:
                    progress = (i + 1) / self.total_files * 100
                    print(f"Progress: {progress:.1f}% ({i + 1}/{self.total_files})")
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                error_count += 1
        
        current_file_hashes = self.get_all_file_hashes()
        self.merkle_detector.build_tree_from_files(current_file_hashes)
        self.cache.store_merkle_state(
            self.merkle_detector.get_root_hash(),
            current_file_hashes
        )
        
        self.cache.cleanup_orphaned_data()
        
        self.last_sync_time = datetime.now()
        
        stats = {
            'total_files': self.total_files,
            'processed_files': processed_count,
            'skipped_files': skipped_count,
            'error_files': error_count,
            'cache_stats': self.cache.get_cache_stats(),
            'vector_db_stats': self.vector_db.get_collection_stats(),
            'embedding_model': self.embeddings.get_model_info(),
            'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None
        }
        
        print("Indexing complete!")
        print(f"Processed: {processed_count}, Skipped: {skipped_count}, Errors: {error_count}")
        
        return stats
    
    def incremental_sync(self, show_progress: bool = True) -> Dict:
        print("Starting incremental sync...")
        
        changes = self.detect_changes()
        
        all_changed_files = changes['added'] | changes['modified'] | changes['deleted']
        
        if not all_changed_files:
            print("No changes detected")
            return {
                'changes_detected': False,
                'added_files': 0,
                'modified_files': 0,
                'deleted_files': 0,
                'processed_files': 0,
                'error_files': 0,
                'cache_stats': self.cache.get_cache_stats(),
                'vector_db_stats': self.vector_db.get_collection_stats(),
                'last_sync': datetime.now().isoformat()
            }
        
        print(f"Changes detected:")
        print(f"  Added: {len(changes['added'])}")
        print(f"  Modified: {len(changes['modified'])}")
        print(f"  Deleted: {len(changes['deleted'])}")
        
        for relative_path in changes['deleted']:
            print(f"Removing deleted file: {relative_path}")
            self.cache.delete_file_data(relative_path)
            self.vector_db.delete_chunks_by_file(relative_path)
        
        files_to_process = []
        for relative_path in changes['added'] | changes['modified']:
            file_path = self.root_path / relative_path
            if file_path.exists():
                files_to_process.append(file_path)
        
        processed_count = 0
        error_count = 0
        
        for i, file_path in enumerate(files_to_process):
            try:
                self.process_file(file_path, force=True)
                processed_count += 1
                
                if show_progress and len(files_to_process) > 10 and (i + 1) % 5 == 0:
                    progress = (i + 1) / len(files_to_process) * 100
                    print(f"Progress: {progress:.1f}% ({i + 1}/{len(files_to_process)})")
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                error_count += 1
        
        self.cache.cleanup_orphaned_data()
        
        self.last_sync_time = datetime.now()
        
        stats = {
            'changes_detected': True,
            'added_files': len(changes['added']),
            'modified_files': len(changes['modified']),
            'deleted_files': len(changes['deleted']),
            'processed_files': processed_count,
            'error_files': error_count,
            'cache_stats': self.cache.get_cache_stats(),
            'vector_db_stats': self.vector_db.get_collection_stats(),
            'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None
        }
        
        print("Incremental sync complete!")
        print(f"Processed: {processed_count}, Errors: {error_count}")
        
        return stats
    
    def get_indexer_status(self) -> Dict:
        return {
            'root_path': str(self.root_path),
            'cache_dir': str(self.cache_dir),
            'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'cache_stats': self.cache.get_cache_stats(),
            'vector_db_stats': self.vector_db.get_collection_stats(),
            'embedding_model': self.embeddings.get_model_info(),
            'merkle_root': self.merkle_detector.get_root_hash()
        }
    
    def clear_cache_if_path_changed(self, show_prompt: bool = True) -> bool:
        cached_path = self.cache.get_indexed_root_path()
        current_path = str(self.root_path.resolve())
        
        if not cached_path:
            return False
        
        if cached_path == current_path:
            return False
        
        cache_stats = self.cache.get_cache_stats()
        
        if cache_stats['files'] == 0:
            return False
        
        print(f"\n Codebase path has changed!")
        print(f"   Previously indexed: {cached_path}")
        print(f"   Current path: {current_path}")
        print(f"   Cache contains: {cache_stats['files']} files, {cache_stats['chunks']} chunks")
        
        if show_prompt:
            response = input("\nClear existing cache and reindex? [Y/n]: ").strip().lower()
            if response in ['n', 'no']:
                print("Keeping existing cache. Results may be incorrect.")
                return False
        
        print("\n🧹 Clearing existing cache...")
        self.cache.clear_all_cache()
        self.vector_db.reset_database()
        
        return True