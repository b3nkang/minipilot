from typing import List
import numpy as np


class LocalEmbeddings:
    def __init__(self, model_name: str = "hkunlp/instructor-xl"):
        self.model_name = model_name
        self.model = None
        self.is_instructor_model = "instructor" in model_name.lower()
        self._load_model()
    
    def _load_model(self):
        import socket
        
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(300)
        
        try:
            print(f"Loading embedding model: {self.model_name}")
            print("Downloading model (this may take a few minutes on first run)...")
            
            if self.is_instructor_model:
                from InstructorEmbedding import INSTRUCTOR
                self.model = INSTRUCTOR(self.model_name)
            else:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
                
            print(f"Model loaded successfully. Embedding dimension: {self.get_embedding_dimension()}")
            
        except Exception as e:
            print(f"Error loading model {self.model_name}: {e}")
            
            if self.is_instructor_model:
                print("Trying alternative instructor model: instructor-large...")
                try:
                    from InstructorEmbedding import INSTRUCTOR
                    self.model_name = "hkunlp/instructor-large"
                    self.model = INSTRUCTOR(self.model_name)
                    print(f"Alternative instructor model loaded. Embedding dimension: {self.get_embedding_dimension()}")
                except Exception as e_large:
                    print(f"instructor-large failed: {e_large}")
                    print("Trying instructor-base...")
                    try:
                        self.model_name = "hkunlp/instructor-base"
                        self.model = INSTRUCTOR(self.model_name)
                        print(f"instructor-base loaded. Embedding dimension: {self.get_embedding_dimension()}")
                    except Exception as e_base:
                        print(f"instructor-base failed: {e_base}")
                        self._fallback_to_minilm()
            else:
                self._fallback_to_minilm()
        finally:
            socket.setdefaulttimeout(original_timeout)
    
    def _fallback_to_minilm(self):
        print("Falling back to all-MiniLM-L6-v2 model...")
        try:
            from sentence_transformers import SentenceTransformer
            self.model_name = "all-MiniLM-L6-v2"
            self.is_instructor_model = False
            self.model = SentenceTransformer(self.model_name)
            print(f"Fallback model loaded. Embedding dimension: {self.get_embedding_dimension()}")
        except Exception as e2:
            print(f"Fallback model also failed: {e2}")
            print("WARNING: Running without embeddings - search will not work properly")
            self.model = None
    
    def get_embedding_dimension(self) -> int:
        if self.model is None:
            return 0
        
        if self.is_instructor_model:
            try:
                return self.model.model.get_sentence_embedding_dimension()
            except:
                if "instructor-xl" in self.model_name:
                    return 768
                elif "instructor-large" in self.model_name:
                    return 768
                elif "instructor-base" in self.model_name:
                    return 768
                else:
                    return 768
        else:
            return self.model.get_sentence_embedding_dimension()
    
    def embed_text(self, text: str, instruction: str = "") -> List[float]:
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        try:
            if self.is_instructor_model and instruction:
                embedding = self.model.encode([[instruction, text]])[0]
            elif self.is_instructor_model:
                embedding = self.model.encode([text])[0]
            else:
                embedding = self.model.encode(text, convert_to_tensor=False)
            
            return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        except Exception as e:
            print(f"Error embedding text: {e}")
            return [0.0] * self.get_embedding_dimension()
    
    def embed_texts(self, texts: List[str], instruction: str = "") -> List[List[float]]:
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        if not texts:
            return []
        
        try:
            if self.is_instructor_model and instruction:
                input_texts = [[instruction, text] for text in texts]
                embeddings = self.model.encode(input_texts)
            elif self.is_instructor_model:
                embeddings = self.model.encode(texts)
            else:
                embeddings = self.model.encode(texts, batch_size=32, convert_to_tensor=False)
            
            if isinstance(embeddings, np.ndarray):
                return embeddings.tolist()
            else:
                return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings]
        
        except Exception as e:
            print(f"Error embedding texts: {e}")
            dim = self.get_embedding_dimension()
            return [[0.0] * dim for _ in texts]
    
    def embed_code_chunk(self, code: str, file_path: str = "") -> List[float]:
        if file_path.endswith('.md'):
            instruction = "Represent the project documentation and content for semantic retrieval:"
        elif file_path.endswith('.astro'):
            instruction = "Represent the website content and component for semantic search:"
        elif file_path.endswith(('.json', '.yaml', '.yml')):
            instruction = "Represent the configuration data for semantic search:"
        else:
            instruction = "Represent the code snippet for semantic search and retrieval:"
        return self.embed_text(code, instruction)
    
    def embed_code_chunks(self, codes: List[str], file_paths: List[str] = None) -> List[List[float]]:
        if file_paths and len(file_paths) == len(codes):
            embeddings = []
            for code, file_path in zip(codes, file_paths):
                embedding = self.embed_code_chunk(code, file_path)
                embeddings.append(embedding)
            return embeddings
        else:
            instruction = "Represent the code snippet for semantic search and retrieval:"
            return self.embed_texts(codes, instruction)
    
    def embed_query(self, query: str) -> List[float]:
        instruction = "Represent the user question for retrieving relevant website content and code snippets:"
        return self.embed_text(query, instruction)
    
    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(dot_product / (norm1 * norm2))
        
        except Exception as e:
            print(f"Error computing similarity: {e}")
            return 0.0
    
    def get_model_info(self) -> dict:
        return {
            'model_name': self.model_name,
            'embedding_dimension': self.get_embedding_dimension(),
            'is_loaded': self.model is not None,
            'is_instructor_model': self.is_instructor_model
        }