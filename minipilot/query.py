from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json

from .vector_db import VectorDatabase
from .embeddings import LocalEmbeddings
from .cache import LocalCache


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    similarity_score: float
    metadata: Dict[str, Any]


@dataclass
class QueryResponse:
    query: str
    results: List[SearchResult]
    total_results: int
    search_time_ms: float
    context_summary: str


class QueryEngine:
    def __init__(self, 
                 cache_dir: str = ".minipilot",
                 max_results: int = 50,
                 similarity_threshold: float = 0.0):
        self.cache_dir = cache_dir
        self.max_results = max_results
        self.similarity_threshold = similarity_threshold
        
        self.vector_db = VectorDatabase(db_path=f"{cache_dir}/chroma_db")
        self.cache = LocalCache(db_path=f"{cache_dir}/cache.db")
        
        cached_model = self._get_cached_embedding_model()
        self.embeddings = LocalEmbeddings(model_name=cached_model)
    
    def search(self, query: str, 
               file_filter: Optional[List[str]] = None,
               max_results: Optional[int] = None) -> QueryResponse:
        import time
        start_time = time.time()
        
        max_results = max_results or self.max_results
        
        query_embedding = self.embeddings.embed_query(query)
        
        search_results = self.vector_db.search(
            query_embedding=query_embedding,
            n_results=max_results * 2,
            file_filter=file_filter
        )
        
        results = []
        query_keywords = self._extract_keywords(query)
        
        for i, (chunk_content, metadata, distance, chunk_id) in enumerate(zip(
            search_results['chunks'],
            search_results['metadatas'],
            search_results['distances'],
            search_results['ids']
        )):
            similarity_score = max(0.0, 1.0 - distance)
            
            boosted_score = self._apply_keyword_boosting(
                similarity_score, chunk_content, query_keywords
            )
            
            if boosted_score < self.similarity_threshold:
                continue
            
            result = SearchResult(
                chunk_id=chunk_id,
                content=chunk_content,
                file_path=metadata.get('file_path', ''),
                start_line=metadata.get('start_line', 0),
                end_line=metadata.get('end_line', 0),
                similarity_score=boosted_score,
                metadata=metadata
            )
            results.append(result)
        
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        results = results[:max_results]
        
        search_time_ms = (time.time() - start_time) * 1000
        
        context_summary = self._generate_context_summary(query, results)
        
        return QueryResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time_ms=search_time_ms,
            context_summary=context_summary
        )
    
    def search_by_file(self, query: str, file_path: str) -> QueryResponse:
        return self.search(query, file_filter=[file_path])
    
    def get_context_for_completion(self, query: str, 
                                 max_context_length: int = 8000,
                                 file_filter: Optional[List[str]] = None,
                                 scan_all_files: bool = False) -> Dict[str, Any]:
        if scan_all_files:
            search_response = self._get_all_chunks_response(query)
        else:
            search_response = self.search(query, file_filter=file_filter, max_results=50)
        
        context_parts = []
        current_length = 0
        
        for result in search_response.results:
            chunk_context = f"""
File: {result.file_path} (lines {result.start_line}-{result.end_line})
```
{result.content}
```
"""
            
            if current_length + len(chunk_context) > max_context_length:
                break
            
            context_parts.append(chunk_context)
            current_length += len(chunk_context)
        
        full_context = "\n".join(context_parts)
        
        return {
            'query': query,
            'context': full_context,
            'context_length': len(full_context),
            'chunks_used': len(context_parts),
            'total_chunks_found': len(search_response.results),
            'search_time_ms': search_response.search_time_ms
        }
    
    def _generate_context_summary(self, query: str, results: List[SearchResult]) -> str:
        if not results:
            return f"No relevant code found for query: '{query}'"
        
        files = {}
        for result in results:
            file_path = result.file_path
            if file_path not in files:
                files[file_path] = []
            files[file_path].append(result)
        
        summary_parts = [f"Found {len(results)} relevant code chunks for query: '{query}'"]
        
        if len(files) == 1:
            file_path = list(files.keys())[0]
            summary_parts.append(f"All results from: {file_path}")
        else:
            summary_parts.append(f"Results from {len(files)} files:")
            for file_path, file_results in files.items():
                summary_parts.append(f"  - {file_path}: {len(file_results)} chunks")
        
        return "\n".join(summary_parts)
    
    def get_related_chunks(self, chunk_id: str, max_results: int = 5) -> List[SearchResult]:
        chunk = self.cache.get_chunk_by_id(chunk_id)
        if not chunk:
            return []
        
        search_response = self.search(chunk['content'], max_results=max_results + 1)
        
        related_results = [
            result for result in search_response.results 
            if result.chunk_id != chunk_id
        ]
        
        return related_results[:max_results]
    
    def explain_code(self, file_path: str, start_line: int, end_line: int) -> Dict[str, Any]:
        file_chunks = self.cache.get_chunks_by_file(file_path)
        
        target_chunks = []
        for chunk in file_chunks:
            if (chunk['start_line'] <= end_line and chunk['end_line'] >= start_line):
                target_chunks.append(chunk)
        
        if not target_chunks:
            return {
                'error': f"No code chunks found for {file_path}:{start_line}-{end_line}"
            }
        
        main_content = "\n".join(chunk['content'] for chunk in target_chunks)
        
        search_response = self.search(main_content, max_results=10)
        
        related_chunks = []
        for result in search_response.results:
            if result.file_path != file_path or not (
                result.start_line <= end_line and result.end_line >= start_line
            ):
                related_chunks.append(result)
        
        return {
            'target_code': main_content,
            'file_path': file_path,
            'line_range': f"{start_line}-{end_line}",
            'related_chunks': related_chunks[:5],
            'context_summary': f"Code explanation context for {file_path}:{start_line}-{end_line}"
        }
    
    def get_query_stats(self) -> Dict[str, Any]:
        return {
            'cache_dir': self.cache_dir,
            'max_results': self.max_results,
            'similarity_threshold': self.similarity_threshold,
            'vector_db_stats': self.vector_db.get_collection_stats(),
            'embedding_model': self.embeddings.get_model_info(),
            'cache_stats': self.cache.get_cache_stats()
        }
    
    def _get_cached_embedding_model(self) -> str:
        try:
            import sqlite3
            with sqlite3.connect(f"{self.cache_dir}/cache.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT embedding_model FROM embeddings LIMIT 1")
                result = cursor.fetchone()
                if result:
                    return result[0]
        except Exception as e:
            print(f"Warning: Could not determine cached embedding model: {e}")
        
        return "hkunlp/instructor-large"
    
    def _get_all_chunks_response(self, query: str) -> QueryResponse:
        import time
        start_time = time.time()
        
        try:
            import sqlite3
            with sqlite3.connect(f"{self.cache_dir}/cache.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT chunk_id, file_path, content, start_line, end_line, chunk_index
                    FROM chunks 
                    ORDER BY file_path, chunk_index
                """)
                
                results = []
                for row in cursor.fetchall():
                    chunk_id, file_path, content, start_line, end_line, chunk_index = row
                    result = SearchResult(
                        chunk_id=chunk_id,
                        content=content,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        similarity_score=1.0,
                        metadata={
                            'file_path': file_path,
                            'start_line': start_line,
                            'end_line': end_line,
                            'chunk_index': chunk_index
                        }
                    )
                    results.append(result)
                
        except Exception as e:
            print(f"Error getting all chunks: {e}")
            results = []
        
        search_time_ms = (time.time() - start_time) * 1000
        
        return QueryResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time_ms=search_time_ms,
            context_summary=f"Retrieved ALL {len(results)} chunks from codebase (workspace mode)"
        )
    
    def _extract_keywords(self, query: str) -> List[str]:
        import re
        words = re.findall(r'\b[a-zA-Z]{2,}\b', query.lower())
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'what', 'who', 'where', 'when', 'why',
            'how', 'this', 'that', 'these', 'those', 'there', 'here', 'it', 'they'
        }
        
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        return keywords
    
    def _apply_keyword_boosting(self, base_score: float, content: str, keywords: List[str]) -> float:
        if not keywords:
            return base_score
        
        content_lower = content.lower()
        boost_factor = 0.0
        
        for keyword in keywords:
            count = content_lower.count(keyword)
            if count > 0:
                keyword_boost = min(0.1 * count, 0.3)
                boost_factor += keyword_boost
        
        boost_factor = min(boost_factor, 0.5)
        boosted_score = base_score + boost_factor * (1 - base_score)
        return min(boosted_score, 1.0)