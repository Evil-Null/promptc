# Changelog

All notable changes to the **Prompt Compiler** (`promptc`) are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.0] — 2025-07-16

### Added

- **`.env` file support** — `python-dotenv` integration for environment variable management
- **`.env.example`** — committed template showing all supported API key formats
- **Claude OAuth/Setup Token auth** — auto-detects `sk-ant-oat01-*` tokens, uses Bearer auth + billing attribution
- **Billing attribution injection** — required for Sonnet/Opus access with OAuth tokens

### Fixed

- **`run` command crash** — `decision.template` → `decision.template_name` (RouteResult attribute fix)
- **`--json` output crash** — `FreeformValidator` returned string status instead of `ValidationStatus` enum
- **`.gitignore`** — `.env` excluded from version control

## [1.1.0] — 2025-07-16

Post-audit quality pass addressing all findings from comprehensive 3-agent audit.

### Added

- **YamlValidator** — heuristic YAML format validation (key: value patterns, structure checks)
- **CodeValidator** — code block detection with prose-rejection heuristic
- **Full-text search** — `mycli logs search --query/-q` searches across all string values in log records
- `__main__.py` entry point test coverage

### Fixed

- Silent exception swallowing in `log_decision()` and `_log_execution()` replaced with debug logging
- Unhandled `OSError`/`UnicodeDecodeError` in `read_daily_log()` now caught gracefully
- Magic numbers `temperature=0.7` / `max_output_tokens=4096` extracted to named constants
- Unused imports removed (`BackendName`, `STRICTNESS_ORDER`)
- Unused variable removed (`hard_passed`)
- CHANGELOG accuracy: corrected to 33 PRs and 7 validators

### Stats

- Validators: 5 → 7 (added yaml, code)
- Tests: 1202 → 1257 (+55 new)
- Files changed: 11

## [1.0.0] — 2025-07-16

First stable release. Eight engineering phases, 33 pull requests, 1202+ tests.

### Phase 1 — CLI Foundation (PR-1)

- CLI skeleton with `version`, `health`, and config system
- XDG-compliant paths for config, data, and logs
- TOML-based configuration with sensible defaults

### Phase 2 — Template Engine (PR-2 through PR-4)

- Pydantic template schema with TOML loader
- Template registry with builtin + custom directory discovery
- Specificity-weighted trigger index with bilingual support (EN/KA)
- 4-zone router: exact → keyword → fuzzy → fallback cascade

### Phase 3 — Compilation Pipeline (PR-5, PR-6)

- Token-budget-aware prompt assembly with 4 compression levels
- Section ordering: system directive → chain of thought → output schema → quality gates → anti-patterns → user input
- Prompt security: user input wrapped in adversarial-resistant delimiters

### Phase 4 — Backend Adapters (PR-7 through PR-10)

- Abstract backend adapter layer with registry and selector
- Compile → adapt boundary hardening with dry-run CLI
- Real HTTP send path via httpx (non-streaming)
- Real streaming passthrough for Claude and GPT via httpx SSE

### Phase 5 — Validation & Quality (PR-11 through PR-13)

- Schema validation layer with 7 format validators (JSON, YAML, Markdown Table, Sections, Numbered List, Code, Freeform)
- Quality gate evaluation with 3 evaluator families
- Retry engine with strictness escalation across compression levels

### Phase 6 — Observability (PR-14 through PR-19)

- JSONL-based decision logging with UTC timestamps
- Derived metrics aggregation (`mycli stats`)
- Log retention pruning (`mycli logs prune`)
- Gzip log rotation with age-based deletion (`mycli logs rotate`)
- Full-text decision log search (`mycli logs search`)
- Period-based log views (`mycli logs today/week/month`)

### Phase 7 — Plugin System (PR-20 through PR-29)

- TOML-based plugin manifest discovery and registry
- Hook execution runtime with failure isolation
- Plugin hooks wired into all 4 pipelines: compile, route, backend, validate
- Plugin health/status reporting integrated into `mycli health --json`
- Sample reference plugin (whitespace-normalizer)
- Thread-based 5-second timeout enforcement per hook
- Plugin install/uninstall helpers with distribution proof

### Phase 8 — Release Readiness (PR-30 through PR-33)

- 46-test release readiness proof covering pipeline, docs, latency, security
- UTC date alignment across all observability and display paths
- CLI display labels aligned to UTC for timezone-independent operation
- Phase 7 closure proof with golden dataset reconfirmation
- CHANGELOG, LICENSE, version bump to 1.0.0

### Fixed

- UTC vs local date mismatch in decision log read/write (PR-31)
- `anti_patterns` TOML root-level key position (PR-6)

### CLI Commands (10)

| Command | Description |
|---------|-------------|
| `mycli version` | Print version |
| `mycli health` | System health check (`--check`, `--strict`, `--json`) |
| `mycli templates` | List available templates |
| `mycli route` | Route input to best template (`--template`, `--json`, `--file`) |
| `mycli compile` | Compile prompt from template (`--template`, `--max-tokens`, `--json`) |
| `mycli run` | Full pipeline: route → compile → send (`--backend`, `--dry-run`, `--stream`) |
| `mycli stats` | Decision metrics (`--json`, `--date`) |
| `mycli plugins` | List installed plugins (`--json`) |
| `mycli backend` | Backend management (`list`, `inspect`) |
| `mycli logs` | Log operations (`--count`, `--json`, `prune`, `rotate`, `search`, `today/week/month`) |
