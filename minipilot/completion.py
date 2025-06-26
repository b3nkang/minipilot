import openai
from typing import Dict, List, Optional, Any
import os
from dataclasses import dataclass

from .query import QueryEngine, QueryResponse


@dataclass
class CompletionRequest:
    query: str
    context_files: Optional[List[str]] = None
    max_tokens: int = 1000
    temperature: float = 0.1
    model: str = "gpt-4o"


@dataclass
class CompletionResponse:
    query: str
    completion: str
    context_used: str
    context_length: int
    chunks_used: int
    search_time_ms: float
    completion_time_ms: float
    total_tokens: Optional[int] = None
    model_used: str = ""


class CompletionEngine:
    def __init__(self, 
                 cache_dir: str = ".minipilot",
                 api_key: Optional[str] = None,
                 max_context_length: int = 16000,
                 dry_run: bool = False):
        self.cache_dir = cache_dir
        self.max_context_length = max_context_length
        
        self.query_engine = QueryEngine(cache_dir=cache_dir)
        api_key = api_key or os.getenv('OPENAI_API_KEY')

        print("API KEY STATUS:\n\n\n")
        if api_key:
            print(f"Using OpenAI API key from environment variable: {api_key[:4]}... (truncated for security)")
        else:
            print("No OpenAI API key provided, running in DRY-RUN mode")
        print("\n\n\nAPI KEY STATUS end")
              
        
        if dry_run or not api_key:
            self.dry_run = True
            self.client = None
            print("Running in DRY-RUN mode - will show retrieved context without calling OpenAI API")
        else:
            self.dry_run = False
            openai.api_key = api_key
            self.client = openai.OpenAI(api_key=api_key)
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        import time
        start_time = time.time()
        
        context_data = self.query_engine.get_context_for_completion(
            query=request.query,
            max_context_length=self.max_context_length,
            file_filter=request.context_files,
            scan_all_files=False
        )
        
        search_time_ms = context_data['search_time_ms']
        
        system_prompt = self._build_system_prompt(context_data['context'])
        
        user_prompt = self._build_user_prompt(request.query)
        
        completion_start = time.time()
        
        # Always show context preview regardless of mode
        context_preview = f"""RETRIEVED CONTEXT PREVIEW:

=== SYSTEM PROMPT ===
{system_prompt}

=== USER PROMPT ===
{user_prompt}

=== CONTEXT ANALYSIS ===
- Query: {request.query}
- Retrieved {context_data['chunks_used']} code chunks
- Total context length: {context_data['context_length']} characters
- Search mode: semantic search
- Model: {request.model}
- Max tokens: {request.max_tokens}
- Temperature: {request.temperature}
"""
        
        print("\n" + "="*80)
        print(context_preview)
        print("="*80)
        
        if self.dry_run:
            completion = context_preview + "\n\nDRY-RUN MODE: No API call made"
            total_tokens = None
        else:
            try:
                response = self.client.chat.completions.create(
                    model=request.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=False
                )
                
                api_completion = response.choices[0].message.content
                total_tokens = response.usage.total_tokens if response.usage else None
                completion = f"API COMPLETION:\n{api_completion}"
                
            except Exception as e:
                completion = f"Error generating completion: {str(e)}"
                total_tokens = None
        
        completion_time_ms = (time.time() - completion_start) * 1000
        
        return CompletionResponse(
            query=request.query,
            completion=completion,
            context_used=context_data['context'],
            context_length=context_data['context_length'],
            chunks_used=context_data['chunks_used'],
            search_time_ms=search_time_ms,
            completion_time_ms=completion_time_ms,
            total_tokens=total_tokens,
            model_used=request.model
        )
    
    def explain_code(self, file_path: str, start_line: int, end_line: int) -> CompletionResponse:
        explanation_context = self.query_engine.explain_code(file_path, start_line, end_line)
        
        if 'error' in explanation_context:
            return CompletionResponse(
                query=f"Explain {file_path}:{start_line}-{end_line}",
                completion=explanation_context['error'],
                context_used="",
                context_length=0,
                chunks_used=0,
                search_time_ms=0,
                completion_time_ms=0,
                model_used="error"
            )
        
        query = f"Explain this code from {file_path}:{start_line}-{end_line}"
        
        context_parts = [f"Target code to explain:\n```\n{explanation_context['target_code']}\n```"]
        
        if explanation_context['related_chunks']:
            context_parts.append("\nRelated code for context:")
            for chunk in explanation_context['related_chunks'][:3]:  # Limit related chunks
                context_parts.append(f"\nFrom {chunk.file_path}:\n```\n{chunk.content}\n```")
        
        context = "\n".join(context_parts)
        
        request = CompletionRequest(
            query=query,
            max_tokens=800,
            temperature=0.1
        )
        
        import time
        start_time = time.time()
        
        system_prompt = self._build_explanation_system_prompt()
        user_prompt = f"{query}\n\n{context}"
        
        try:
            response = self.client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stream=False
            )
            
            completion = response.choices[0].message.content
            total_tokens = response.usage.total_tokens if response.usage else None
            
        except Exception as e:
            completion = f"Error generating explanation: {str(e)}"
            total_tokens = None
        
        completion_time_ms = (time.time() - start_time) * 1000
        
        return CompletionResponse(
            query=query,
            completion=completion,
            context_used=context,
            context_length=len(context),
            chunks_used=len(explanation_context['related_chunks']) + 1,
            search_time_ms=0,  # No search needed for explanation
            completion_time_ms=completion_time_ms,
            total_tokens=total_tokens,
            model_used=request.model
        )
    
    def chat_about_codebase(self, message: str, 
                           context_files: Optional[List[str]] = None,
                           conversation_history: Optional[List[Dict]] = None) -> CompletionResponse:
        request = CompletionRequest(
            query=message,
            context_files=context_files,
            max_tokens=1200,
            temperature=0.2
        )
        
        context_data = self.query_engine.get_context_for_completion(
            query=message,
            max_context_length=self.max_context_length,
            file_filter=context_files
        )
        
        messages = [
            {"role": "system", "content": self._build_chat_system_prompt(context_data['context'])}
        ]
        
        if conversation_history:
            messages.extend(conversation_history[-10:])  # Keep last 10 messages
        
        messages.append({"role": "user", "content": message})
        
        import time
        completion_start = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model=request.model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stream=False
            )
            
            completion = response.choices[0].message.content
            total_tokens = response.usage.total_tokens if response.usage else None
            
        except Exception as e:
            completion = f"Error in chat: {str(e)}"
            total_tokens = None
        
        completion_time_ms = (time.time() - completion_start) * 1000
        
        return CompletionResponse(
            query=message,
            completion=completion,
            context_used=context_data['context'],
            context_length=context_data['context_length'],
            chunks_used=context_data['chunks_used'],
            search_time_ms=context_data['search_time_ms'],
            completion_time_ms=completion_time_ms,
            total_tokens=total_tokens,
            model_used=request.model
        )
    
    def _build_system_prompt(self, context: str) -> str:
        return f"""You are an AI coding assistant, powered by Claude Sonnet 4. You operate in Cursor.

You are pair programming with a USER to solve their coding task. Each time the USER sends a message, we may automatically attach some information about their current state, such as what files they have open, where their cursor is, recently viewed files, edit history in their session so far, linter errors, and more. This information may or may not be relevant to the coding task, it is up for you to decide.

Your main goal is to follow the USER's instructions at each message.

<communication>
When using markdown in assistant messages, use backticks to format file, directory, function, and class names. Use \\( and \\) for inline math, \\[ and \\] for block math.
</communication>

<relevant_code_context>
{context}
</relevant_code_context>

<guidelines>
- Use the provided code context to understand the codebase structure and patterns
- Follow the existing code style and conventions
- Provide practical, working code solutions
- Explain your reasoning when helpful
- If the context doesn't contain relevant information, say so clearly
- Use backticks to format file, directory, function, and class names
</guidelines>

You MUST use the following format when citing code regions or blocks:
```12:15:app/components/Todo.tsx
// ... existing code ...
```
This is the ONLY acceptable format for code citations. The format is ```startLine:endLine:filepath where startLine and endLine are line numbers."""
    
    def _build_explanation_system_prompt(self) -> str:
        return """You are an expert software developer who excels at explaining code clearly and concisely.

Your role is to explain code sections, including:
- What the code does (high-level purpose)
- How it works (key logic and flow)  
- Important details (algorithms, patterns, edge cases)
- Context and relationships to other parts of the codebase

Guidelines:
- Provide clear, structured explanations
- Use appropriate technical detail for the audience
- Highlight important patterns or design decisions
- Mention potential issues or areas for improvement if relevant
- Be concise but thorough"""
    
    def _build_chat_system_prompt(self, context: str) -> str:
        return f"""You are a knowledgeable assistant who can answer questions about this codebase.

Relevant code context:
{context}

Your role is to:
- Answer questions about the codebase structure and functionality
- Help understand how different parts work together
- Suggest improvements or point out potential issues
- Provide guidance on development tasks

Guidelines:
- Base your answers on the provided context when possible
- Be helpful and conversational while remaining technical
- Ask clarifying questions if needed
- Acknowledge when you don't have enough context to answer fully"""
    
    def _build_user_prompt(self, query: str) -> str:
        return f"""Please help me with the following request:

{query}

Based on the relevant code context provided, please provide a helpful response."""
    
    def get_completion_stats(self) -> Dict[str, Any]:
        return {
            'cache_dir': self.cache_dir,
            'max_context_length': self.max_context_length,
            'query_engine_stats': self.query_engine.get_query_stats(),
            'openai_configured': bool(os.getenv('OPENAI_API_KEY'))
        }