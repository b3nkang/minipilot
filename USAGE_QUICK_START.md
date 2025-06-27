# Minipilot Quick Start Guide

## Quick Start

### Default Usage

```bash
python start_web.py
```

This will prompt you for whether you want to use an existing cache or a path to a new codebase entirely. Only necessary on launch of Minipilot.

### Custom Codebase Path

```bash
python start_web.py /path/to/your/codebase
```

### Custom Port

```bash
python start_web.py --port 9000
```

### Custom Codebase + Port

```bash
python start_web.py /Users/yourname/projects/myproject --port 9000
```

## Direct Server Usage

### Default Usage

```bash
python web_server.py
```

### With Custom Path

```bash
python web_server.py /path/to/your/codebase
```

### All Options

```bash
python web_server.py /path/to/your/codebase --port 9000 --cache-dir my_cache
```

## Examples

### Index a React Project

```bash
python start_web.py ~/projects/my-react-app
```

### Index Current Directory

```bash
python start_web.py .
```

### Index with Custom Cache Location

```bash
python web_server.py ~/projects/backend --cache-dir ~/minipilot-cache
```

## Command Line Arguments

### start_web.py

- `codebase_path` (optional) - Path to codebase to index
- `--port` / `-p` - Port number (default: 8000)

### web_server.py

- `codebase_path` (optional) - Path to codebase to index
- `--port` / `-p` - Port number (default: 8000)
- `--cache-dir` / `-c` - Cache directory (default: .minipilot)

## Notes

- If no path is provided (default usage), then user will be prompted to pick from cache or enter a new codebase path.
- Paths are automatically expanded (~ becomes home directory)
- Paths are converted to absolute paths
- Server validates that the specified path exists before starting
