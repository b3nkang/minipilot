#!/usr/bin/env python3

from dotenv import load_dotenv
load_dotenv()

from minipilot.indexer import CodebaseIndexer
from minipilot.completion import CompletionEngine, CompletionRequest


def main():
    print("Minipilot Dry-Run Demo")
    print("=" * 50)
    import os
    codebase_path = os.path.expanduser("~/repos/fsab/fullstackatbrown.com/")
    cache_dir = ".minipilot"
    
    if not os.path.exists(codebase_path):
        print(f"Path {codebase_path} doesn't exist, using current directory instead")
        codebase_path = "."
    
    print(f"\n1. Ensuring codebase is indexed...")
    print(f"   Target directory: {codebase_path}")
    
    indexer = CodebaseIndexer(root_path=codebase_path, cache_dir=cache_dir)
    
    cache_stats = indexer.cache.get_cache_stats()
    if cache_stats['chunks'] == 0:
        print("   No existing cache found, performing full indexing...")
        stats = indexer.full_index(show_progress=True)
    else:
        stats = indexer.incremental_sync(show_progress=False)
    
    print(f"   Cache has {stats['cache_stats']['chunks']} chunks ready")
    
    print("\n2. OpenAI API call...")
    completion_engine = CompletionEngine(cache_dir=cache_dir, dry_run=False)
    
    request = CompletionRequest(
        query="What is OLEEP and who manages it?",
        max_tokens=800,
        temperature=0.1
    )
    
    response = completion_engine.complete(request)
    
    print("\n" + "="*80)
    print("API RESPONSE RESULTS:")
    print("="*80)
    print(response.completion)
    print("="*80)
    
    print(f"\nStats:")
    print(f"   • Search time: {response.search_time_ms:.1f}ms")
    print(f"   • Chunks retrieved: {response.chunks_used}")
    print(f"   • Context length: {response.context_length} characters")
    
    print(f"\nThis shows exactly what would be sent to OpenAI!")
    print(f"To get actual completion, set OPENAI_API_KEY environment variable")


if __name__ == "__main__":
    main()