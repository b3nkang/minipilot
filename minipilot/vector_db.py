
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional, Any
from pathlib import Path


class VectorDatabase:
    def __init__(self, db_path: str = ".minipilot/chroma_db"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        self.collection = self.client.get_or_create_collection(
            name="code_chunks",
            metadata={"description": "Code chunks for semantic search"}
        )
    
    def add_chunk(self, chunk_id: str, content: str, embedding: List[float], 
                  metadata: Dict[str, Any]):
        try:
            self.collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
        except Exception as e:
            self.collection.update(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
    
    def add_chunks(self, chunks: List[Dict]):
        if not chunks:
            return
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            ids.append(chunk['chunk_id'])
            embeddings.append(chunk['embedding'])
            documents.append(chunk['content'])
            metadatas.append({
                'file_path': chunk['file_path'],
                'start_line': chunk['start_line'],
                'end_line': chunk['end_line'],
                'chunk_index': chunk['chunk_index'],
                'token_count': chunk['token_count'],
                'chunk_hash': chunk['chunk_hash']
            })
        
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            for i, chunk in enumerate(chunks):
                try:
                    self.collection.add(
                        ids=[ids[i]],
                        embeddings=[embeddings[i]],
                        documents=[documents[i]],
                        metadatas=[metadatas[i]]
                    )
                except:
                    self.collection.update(
                        ids=[ids[i]],
                        embeddings=[embeddings[i]],
                        documents=[documents[i]],
                        metadatas=[metadatas[i]]
                    )
    
    def search(self, query_embedding: List[float], n_results: int = 10, 
               file_filter: Optional[List[str]] = None) -> Dict:
        where_clause = None
        if file_filter:
            where_clause = {"file_path": {"$in": file_filter}}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_clause,
            include=['documents', 'metadatas', 'distances']
        )
        
        return {
            'chunks': results['documents'][0] if results['documents'] else [],
            'metadatas': results['metadatas'][0] if results['metadatas'] else [],
            'distances': results['distances'][0] if results['distances'] else [],
            'ids': results['ids'][0] if results['ids'] else []
        }
    
    def get_chunk(self, chunk_id: str) -> Optional[Dict]:
        try:
            results = self.collection.get(
                ids=[chunk_id],
                include=['documents', 'metadatas']
            )
            
            if results['ids']:
                return {
                    'chunk_id': results['ids'][0],
                    'content': results['documents'][0],
                    'metadata': results['metadatas'][0]
                }
        except:
            pass
        
        return None
    
    def delete_chunk(self, chunk_id: str):
        try:
            self.collection.delete(ids=[chunk_id])
        except:
            pass
    
    def delete_chunks_by_file(self, file_path: str):
        try:
            self.collection.delete(
                where={"file_path": file_path}
            )
        except:
            pass
    
    def update_chunk(self, chunk_id: str, content: str, embedding: List[float], 
                     metadata: Dict[str, Any]):
        try:
            self.collection.update(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
        except:
            self.add_chunk(chunk_id, content, embedding, metadata)
    
    def get_collection_stats(self) -> Dict:
        try:
            count = self.collection.count()
            return {
                'total_chunks': count,
                'collection_name': self.collection.name
            }
        except:
            return {
                'total_chunks': 0,
                'collection_name': self.collection.name
            }
    
    def list_files(self) -> List[str]:
        try:
            results = self.collection.get(include=['metadatas'])
            file_paths = set()
            
            for metadata in results['metadatas']:
                if 'file_path' in metadata:
                    file_paths.add(metadata['file_path'])
            
            return sorted(list(file_paths))
        except:
            return []
    
    def reset_database(self):
        try:
            self.client.delete_collection(name="code_chunks")
            self.collection = self.client.create_collection(
                name="code_chunks",
                metadata={"description": "Code chunks for semantic search"}
            )
        except:
            pass
    
    def search_by_text(self, query_text: str, n_results: int = 10) -> Dict:
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                include=['documents', 'metadatas', 'distances']
            )
            
            return {
                'chunks': results['documents'][0] if results['documents'] else [],
                'metadatas': results['metadatas'][0] if results['metadatas'] else [],
                'distances': results['distances'][0] if results['distances'] else [],
                'ids': results['ids'][0] if results['ids'] else []
            }
        except:
            return {
                'chunks': [],
                'metadatas': [],
                'distances': [],
                'ids': []
            }