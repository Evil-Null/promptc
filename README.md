# Prompt Compiler

Universal CLI Prompt Compiler — elite prompt engineering, automatically.

## Install

```bash
pip install -e .
```

## Usage

```bash
mycli --help
mycli version
```

### Health checks

```bash
mycli health
mycli health --check config_valid
mycli health --strict
mycli health --json
```

### Templates

```bash
mycli templates
```

### Routing

```bash
mycli route "review this code for bugs"
mycli route "review this code" --template code-review
mycli route "review this code" --json
mycli route "review this code" --file main.py
```

### Compilation

```bash
mycli compile "explain this function" --template explain
mycli compile "explain this function" --template explain --max-tokens 4096
mycli compile "explain this function" --template explain --json
```

### Run (compile + route + adapt)

```bash
mycli run "review my auth module" --backend claude --dry-run
mycli run "review my auth module" --backend claude --json
mycli run "review my auth module" --backend claude --stream
mycli run "review my auth module" --template code-review --backend gpt
```

### Backend inspection

```bash
mycli backend list
mycli backend inspect claude
```

### Decision logs

```bash
mycli logs
mycli logs --count 20 --json
mycli logs today
mycli logs week
mycli logs month
mycli logs search "code-review"
mycli logs prune --days 30
mycli logs rotate
```

### Metrics

```bash
mycli stats
mycli stats --date 2025-01-15 --json
```

### Plugins

```bash
mycli plugins
mycli plugins --json
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
