
import argparse
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.syntax import Syntax

from .indexer import CodebaseIndexer
from .query import QueryEngine
from .completion import CompletionEngine, CompletionRequest


console = Console()


def cmd_index(args):
    project_path = args.path if args.path else args.project_root
    cache_path = Path(project_path) / args.cache_dir
    
    console.print(f"[bold green]Indexing codebase at: {project_path}[/bold green]")
    console.print(f"[dim]Cache directory: {cache_path}[/dim]")
    
    indexer = CodebaseIndexer(
        root_path=project_path,
        cache_dir=str(cache_path),
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )
    
    try:
        if args.incremental:
            stats = indexer.incremental_sync(show_progress=True)
        else:
            stats = indexer.full_index(show_progress=True)
        
        table = Table(title="Indexing Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        if args.incremental:
            table.add_row("Changes Detected", str(stats['changes_detected']))
            table.add_row("Added Files", str(stats['added_files']))
            table.add_row("Modified Files", str(stats['modified_files']))
            table.add_row("Deleted Files", str(stats['deleted_files']))
            table.add_row("Processed Files", str(stats['processed_files']))
        else:
            table.add_row("Total Files", str(stats['total_files']))
            table.add_row("Processed Files", str(stats['processed_files']))
            table.add_row("Skipped Files", str(stats['skipped_files']))
            table.add_row("Error Files", str(stats['error_files']))
        
        table.add_row("Total Chunks", str(stats['cache_stats']['chunks']))
        table.add_row("Total Embeddings", str(stats['cache_stats']['embeddings']))
        table.add_row("Vector DB Chunks", str(stats['vector_db_stats']['total_chunks']))
        
        console.print(table)
        
        if args.json:
            console.print(json.dumps(stats, indent=2))
            
    except Exception as e:
        console.print(f"[bold red]Error during indexing: {e}[/bold red]")
        sys.exit(1)


def cmd_search(args):
    cache_path = Path(args.project_root) / args.cache_dir
    query_engine = QueryEngine(cache_dir=str(cache_path))
    
    try:
        response = query_engine.search(
            query=args.query,
            file_filter=args.files,
            max_results=args.max_results
        )
        
        if not response.results:
            console.print(f"[yellow]No results found for: {args.query}[/yellow]")
            return
        
        console.print(f"[bold green]Found {response.total_results} results in {response.search_time_ms:.1f}ms[/bold green]\n")
        
        for i, result in enumerate(response.results, 1):
            title = f"Result {i}: {result.file_path}:{result.start_line}-{result.end_line}"
            similarity = f"Similarity: {result.similarity_score:.3f}"
            
            syntax = Syntax(result.content, "python", theme="monokai", line_numbers=True, start_line=result.start_line)
            
            panel = Panel(
                syntax,
                title=f"{title} ({similarity})",
                title_align="left",
                border_style="blue"
            )
            console.print(panel)
            console.print()
        
        if args.json:
            json_results = []
            for result in response.results:
                json_results.append({
                    'chunk_id': result.chunk_id,
                    'file_path': result.file_path,
                    'start_line': result.start_line,
                    'end_line': result.end_line,
                    'similarity_score': result.similarity_score,
                    'content': result.content
                })
            
            console.print(json.dumps({
                'query': response.query,
                'total_results': response.total_results,
                'search_time_ms': response.search_time_ms,
                'results': json_results
            }, indent=2))
            
    except Exception as e:
        console.print(f"[bold red]Error during search: {e}[/bold red]")
        sys.exit(1)


def cmd_complete(args):
    try:
        cache_path = Path(args.project_root) / args.cache_dir
        completion_engine = CompletionEngine(
            cache_dir=str(cache_path),
            dry_run=args.dry_run
        )
        
        request = CompletionRequest(
            query=args.query,
            context_files=args.files,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            model=args.model
        )
        
        response = completion_engine.complete(request)
        
        console.print(f"[bold green]Code Completion[/bold green]")
        console.print(f"[dim]Search time: {response.search_time_ms:.1f}ms, Completion time: {response.completion_time_ms:.1f}ms[/dim]")
        console.print(f"[dim]Context: {response.chunks_used} chunks, {response.context_length} chars[/dim]\n")
        
        syntax = Syntax(response.completion, "python", theme="monokai")
        panel = Panel(
            syntax,
            title="Generated Code",
            title_align="left",
            border_style="green"
        )
        console.print(panel)
        
        if args.show_context:
            console.print("\n[bold cyan]Context Used:[/bold cyan]")
            context_syntax = Syntax(response.context_used, "python", theme="monokai")
            context_panel = Panel(
                context_syntax,
                title="Retrieved Context",
                title_align="left",
                border_style="cyan"
            )
            console.print(context_panel)
        
        if args.json:
            console.print(json.dumps({
                'query': response.query,
                'completion': response.completion,
                'context_length': response.context_length,
                'chunks_used': response.chunks_used,
                'search_time_ms': response.search_time_ms,
                'completion_time_ms': response.completion_time_ms,
                'total_tokens': response.total_tokens
            }, indent=2))
            
    except Exception as e:
        console.print(f"[bold red]Error during completion: {e}[/bold red]")
        sys.exit(1)


def cmd_explain(args):
    try:
        cache_path = Path(args.project_root) / args.cache_dir
        completion_engine = CompletionEngine(
            cache_dir=str(cache_path),
            dry_run=getattr(args, 'dry_run', False)
        )
        
        response = completion_engine.explain_code(
            file_path=args.file,
            start_line=args.start_line,
            end_line=args.end_line
        )
        
        console.print(f"[bold green]Code Explanation: {args.file}:{args.start_line}-{args.end_line}[/bold green]\n")
        
        panel = Panel(
            response.completion,
            title="Explanation",
            title_align="left",
            border_style="green"
        )
        console.print(panel)
        
        if args.show_context:
            console.print("\n[bold cyan]Context Used:[/bold cyan]")
            context_syntax = Syntax(response.context_used, "python", theme="monokai")
            context_panel = Panel(
                context_syntax,
                title="Code Context",
                title_align="left",
                border_style="cyan"
            )
            console.print(context_panel)
            
    except Exception as e:
        console.print(f"[bold red]Error during explanation: {e}[/bold red]")
        sys.exit(1)


def cmd_status(args):
    try:
        cache_path = Path(args.project_root) / args.cache_dir
        indexer = CodebaseIndexer(root_path=args.project_root, cache_dir=str(cache_path))
        status = indexer.get_indexer_status()
        
        table = Table(title="Minipilot Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="white")
        
        table.add_row("Root Path", status['root_path'])
        table.add_row("Cache Directory", status['cache_dir'])
        table.add_row("Last Sync", status['last_sync'] or "Never")
        table.add_row("Merkle Root", status['merkle_root'][:16] + "..." if status['merkle_root'] else "None")
        
        table.add_row("", "")
        table.add_row("Files Cached", str(status['cache_stats']['files']))
        table.add_row("Chunks Cached", str(status['cache_stats']['chunks']))
        table.add_row("Embeddings Cached", str(status['cache_stats']['embeddings']))
        
        table.add_row("", "")
        table.add_row("Vector DB Chunks", str(status['vector_db_stats']['total_chunks']))
        table.add_row("Embedding Model", status['embedding_model']['model_name'])
        table.add_row("Embedding Dimension", str(status['embedding_model']['embedding_dimension']))
        
        console.print(table)
        
        if args.json:
            console.print(json.dumps(status, indent=2))
            
    except Exception as e:
        console.print(f"[bold red]Error getting status: {e}[/bold red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Minipilot - Local AI Code Assistant")
    parser.add_argument("--cache-dir", default=".minipilot", help="Cache directory (relative to project root)")
    parser.add_argument("--project-root", default=".", help="Path to project root directory")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    index_parser = subparsers.add_parser("index", help="Index the codebase")
    index_parser.add_argument("path", nargs="?", help="Path to codebase root (overrides --project-root)")
    index_parser.add_argument("--incremental", action="store_true", help="Incremental indexing")
    index_parser.add_argument("--chunk-size", type=int, default=1000, help="Chunk size in tokens")
    index_parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap in tokens")
    index_parser.set_defaults(func=cmd_index)
    
    search_parser = subparsers.add_parser("search", help="Search the codebase")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--files", nargs="*", help="Limit search to specific files")
    search_parser.add_argument("--max-results", type=int, default=10, help="Maximum results")
    search_parser.set_defaults(func=cmd_search)
    
    complete_parser = subparsers.add_parser("complete", help="Generate code completion")
    complete_parser.add_argument("query", help="Completion query/prompt")
    complete_parser.add_argument("--files", nargs="*", help="Limit context to specific files")
    complete_parser.add_argument("--max-tokens", type=int, default=1000, help="Max completion tokens")    
    complete_parser.add_argument("--temperature", type=float, default=0.1, help="Completion temperature")
    complete_parser.add_argument("--model", default="gpt-4", help="OpenAI model to use")
    complete_parser.add_argument("--show-context", action="store_true", help="Show retrieved context")
    complete_parser.add_argument("--dry-run", action="store_true", help="Show context without calling OpenAI API")
    complete_parser.set_defaults(func=cmd_complete)
    
    explain_parser = subparsers.add_parser("explain", help="Explain code section")
    explain_parser.add_argument("file", help="File path")
    explain_parser.add_argument("start_line", type=int, help="Start line number")
    explain_parser.add_argument("end_line", type=int, help="End line number")
    explain_parser.add_argument("--show-context", action="store_true", help="Show retrieved context")
    explain_parser.add_argument("--dry-run", action="store_true", help="Show context without calling OpenAI API")
    explain_parser.set_defaults(func=cmd_explain)
    
    status_parser = subparsers.add_parser("status", help="Show Minipilot status")
    status_parser.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()