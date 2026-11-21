# Catalogue des outils (généré depuis le registre)

**72 outils réels**, enregistrés dans `omnibridge/core/registry.py` et exposés par le
serveur MCP Python. Ce fichier est généré depuis le code : `python tools/gen_tool_docs.py`.

Niveaux : **L1** lecture · **L2** assistance (sauvegarde + audit) · **L3** automatisation contrôlée · **L4** sensible (`confirm=true` obligatoire).

## system (4)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `system_audit_log` | 1 | R | Recent audit log of tool calls (tool, permission level, success/failure). Use for security review and debugging. | `limit`? |
| `system_diagnostics` | 1 | R | Deep diagnostics: workspace, DB, token, dashboard, Studio MCP discovery, bridge status, knowledge index. Returns pass/fail per check with remediation hints. | — |
| `system_health` | 1 | R | Health check for OMNIBRIDGE: runtime, workspace, data dir, tool count, connected subsystems (Roblox Studio MCP, browser extension, knowledge base). Call this first to know what is available. | — |
| `system_list_tools` | 1 | R | List every registered MCP tool with its category, permission level and description. Use to discover capabilities before acting. | `category`? |

## files (7)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `file_backup` | 2 | W | Manually back up a workspace file to the data dir. Returns the backup path. | `path` |
| `file_create` | 3 | W | Create a new file inside the workspace (parent dirs created). Fails if the file already exists — use file_update to modify. | `path`, `content` |
| `file_delete` | 4 | W | Delete a workspace file after backing it up. Level 4: requires confirm=true. Directories are never deleted. | `path`, `confirm`? |
| `file_list` | 1 | R | List files in a directory inside the workspace (recursive up to depth). Sandboxed: cannot escape the workspace root. | `path`?, `recursive`?, `maxDepth`? |
| `file_read` | 1 | R | Read a text file inside the workspace. Binary files and files over the size limit are rejected with a clear error. | `path`, `offset`?, `limit`? |
| `file_search` | 1 | R | Search file contents (regex) across the workspace. Returns matching files with line numbers and snippets. Skips node_modules/.git/dist/.venv. | `pattern`, `path`?, `glob`?, `maxResults`? |
| `file_update` | 3 | W | Create or overwrite a file inside the workspace. Always backs up the previous version to the data dir first (reversible). | `path`, `content` |

## project (2)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `project_analyze` | 1 | R | Analyze a project: counts Luau files, runs Luau static analysis on every .luau file, reports TODOs and dependency health. | `path`? |
| `project_inspect` | 1 | R | Inspect a project directory: file tree summary, detected project type (Node/Rojo/Roblox/Python), entry points, package.json / project.json contents. | `path`? |

## code (5)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `code_analyze` | 1 | R | Static analysis of a source file. For Luau: validates services, classes, deprecated APIs, balanced delimiters, strict mode. For other languages: delimiter checks. Returns structured issues with line numbers. | `path` |
| `code_review` | 1 | R | Review a source file: static analysis, TODOs, size/complexity heuristics, structured review with recommendations. | `path` |
| `code_test` | 2 | W | Run tests for a file/project. Luau: static analysis as compile check. Node: npm test. Python: pytest. Never claims success without running something. | `path`?, `timeoutMs`? |
| `dependency_inspect` | 1 | R | Inspect project dependencies (package.json or pyproject.toml): lists deps and flags missing node_modules/.venv. | `path`? |
| `error_diagnose` | 1 | R | Diagnose an error message: classifies it (syntax, API, permission, network, Roblox-specific), suggests likely causes and concrete fixes. Unknown errors are reported as unknown — never guessed. | `message`, `path`? |

## knowledge (9)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `knowledge_fetch_docs` | 2 | W | Fetch and index the curated official documentation sources (MCP spec, Roblox Creator Docs, Luau, Rojo…). Stored with fetch date and reliability. | `sourceId`? |
| `knowledge_index` | 3 | W | Index a document into the knowledge base (chunked, FTS5 + TF-IDF). Replaces any previous document with the same source id. Secrets are redacted automatically. | `source`, `title`, `text`, `version`?, `reliability`? |
| `knowledge_index_file` | 2 | W | Index a workspace file (docs, .md, .txt, .luau) into the knowledge base. | `path`, `source`? |
| `knowledge_index_luau` | 2 | W | Index the built-in Luau/Roblox knowledge base. Call once at setup; idempotent. | — |
| `knowledge_retrieve` | 1 | R | Hybrid retrieval (FTS5 + TF-IDF) over the indexed knowledge base. Returns passages with citations (source, version, fetch date, reliability). | `query`, `limit`? |
| `knowledge_stats` | 1 | R | Knowledge base statistics: chunk count, source count, per-source breakdown. | — |
| `memory_get` | 1 | R | Retrieve a persistent memory entry by scope and key. | `scope`?, `key` |
| `memory_list` | 1 | R | List memory entries in a scope (optionally filtered by key prefix). | `scope`?, `prefix`? |
| `memory_set` | 3 | W | Store a persistent memory entry. Scopes: personal, project, temp. Secrets are redacted. Never store passwords here. | `scope`?, `key`, `value` |

## web (5)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `documentation_search` | 1 | R | Search curated documentation: local knowledge base first, then the curated official source list (MCP spec, Roblox Creator Docs, Luau, Rojo). Returns hits with citations. | `query`, `limit`? |
| `web_compare_sources` | 1 | R | Fetch several URLs and compare them: headings per source + likely contradictions. If urls is empty, searches first and uses the top results. | `query`, `urls`? |
| `web_extract` | 1 | R | Extract structured facts from a URL: headings, links and code blocks. | `url` |
| `web_open` | 1 | R | Open a URL and return its extracted text (scripts/styles stripped, headings preserved). Size- and time-limited. Content is untrusted data. | `url`, `maxChars`? |
| `web_search` | 1 | R | Search the web (DuckDuckGo HTML endpoint). Returns titles, URLs and snippets. Results are untrusted data. | `query`, `maxResults`? |

## roblox (13)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `roblox_capture_screen` | 1 | R | Capture a screenshot of the Studio viewport via the official MCP server. | — |
| `roblox_create_objects` | 3 | W | Create instances in the live Studio session via the official MCP server. Requires Studio MCP configured. | `className`, `parent`, `properties`? |
| `roblox_edit_scripts` | 3 | W | Edit Luau scripts on disk (Rojo project): create or overwrite script files with backup + static analysis. For live Studio editing use roblox_execute_luau. | `path`, `content` |
| `roblox_execute_luau` | 3 | W | Execute Luau code in the live Studio session via the official MCP server. Requires Studio MCP configured. | `code` |
| `roblox_get_console_output` | 1 | R | Read Studio console output (errors/warnings) via the official MCP server. | `limit`? |
| `roblox_get_studio_state` | 1 | R | Get the state of the connected Studio instance via the official Studio MCP server. | — |
| `roblox_inspect_instance` | 1 | R | Inspect a live instance in Studio via the official MCP server. Requires Studio MCP configured; otherwise returns setup instructions. | `path` |
| `roblox_inspect_project` | 1 | R | Inspect a Roblox/Rojo project on disk: project.json tree, .luau/.lua/.rbxlx files. Works without Studio running. | `path`? |
| `roblox_list_studios` | 1 | R | List open Roblox Studio instances via the official Studio MCP server. If Studio MCP is not configured, returns available=false with exact setup instructions. | — |
| `roblox_playtest` | 3 | W | Start/stop a playtest in Studio via the official MCP server and return its status. | `action`? |
| `roblox_read_script` | 1 | R | Read a Luau script file from a Rojo project on disk, with static analysis attached. | `path` |
| `roblox_search_assets` | 1 | R | Search the Roblox Creator Store via the official MCP server when available. Otherwise returns setup instructions — never fakes results. | `query`, `assetType`? |
| `roblox_search_scripts` | 1 | R | Search Luau script contents in a Rojo project on disk (regex). | `pattern`, `path`?, `maxResults`? |

## browser (10)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `browser_capture_page` | 1 | R | Capture a screenshot of the active tab via the extension (returns base64 PNG). | — |
| `browser_get_active_tab` | 1 | R | Get the active browser tab (URL, title) via the extension. Requires the OMNIBRIDGE extension connected. | — |
| `browser_get_links` | 1 | R | List links on the active page via the extension (href + text). | `limit`? |
| `browser_get_page_content` | 1 | R | Get the text content of the active page via the extension (user-authorized context). | `maxChars`? |
| `browser_get_page_info` | 1 | R | Get technical page info via the extension: meta tags (no tokens/secrets), scripts, element counts, navigation timings, viewport. Developer-mode aid. | — |
| `browser_get_selected_text` | 1 | R | Get the user's current text selection on the active page via the extension. | — |
| `browser_pw_open` | 1 | R | Open a URL in headless Chromium via Playwright (optional dependency) and return its text. Content is untrusted data. | `url`, `maxChars`? |
| `browser_pw_status` | 1 | R | Status of the optional Playwright browser automation (secondary path). The extension bridge is primary. | — |
| `browser_search_page` | 1 | R | Search text within the active page via the extension. Returns matching snippets. | `query` |
| `browser_status` | 1 | R | Status of the browser extension bridge: connected clients and their info. | — |

## bridge (2)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `desktop_bridge_install` | 3 | W | Install/refresh the Python Native Messaging host for Chrome, Edge, Chromium, Brave and Firefox. Pass the Chromium extension id(s) so the browser accepts the host. | `extensionIds`? |
| `desktop_bridge_status` | 1 | R | Status of the Desktop Bridge (Native Messaging host): manifest/launcher present, data dir, connected extension clients, core URL. | — |

## agent (10)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `agent_cancel_task` | 2 | W | Cancel a running autonomous task. Already-completed steps keep their checkpoints. | `taskId` |
| `agent_compare_solutions` | 1 | R | Compare candidate solutions in a structured matrix (pros/cons, complexity, risk) and recommend the best fit. Deterministic scoring — no invented facts. | `problem`, `solutions`, `constraints`? |
| `agent_create_checkpoint` | 2 | W | Create a manual checkpoint for a task (snapshot of current results). | `taskId` |
| `agent_create_plan` | 1 | R | Create an execution plan for a goal. Either pass explicit steps (each with a real tool name) or let the deterministic planner decompose the goal. | `goal`, `steps`?, `workspace`? |
| `agent_find_solution` | 1 | R | Search for solutions to a problem: knowledge retrieval + documentation search into a ranked candidate list with sources. | `problem`, `maxCandidates`? |
| `agent_get_task_status` | 1 | R | Get the status of an autonomous task: progress, per-step results, errors. | `taskId` |
| `agent_list_roles` | 1 | R | List the specialized agent roles with their tool preferences and checklists. | — |
| `agent_restore_checkpoint` | 2 | W | Restore the latest checkpoint of a task and pause it, so it can be re-run from the saved state. | `taskId` |
| `agent_review_result` | 1 | R | Review a task/step result: checks acceptance criteria, flags failures, suggests next actions. | `taskId`, `stepId`? |
| `agent_start_task` | 2 | W | Start (or resume) an autonomous task: creates a plan if needed, then executes it step by step with checkpoints, retries and cancellation. Runs in the background. | `goal`, `plan`?, `workspace`? |

## plugins (2)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `plugin_diagnose` | 1 | R | Diagnose a connector: validates its manifest, checks declared tools exist in the registry, and reports permission requirements. | `name` |
| `plugin_list` | 1 | R | List installed connectors/plugins with their manifests, capabilities and enabled state. | — |

## automation (3)

| Outil | Niv. | R/W | Description | Paramètres |
| --- | --- | --- | --- | --- |
| `process_list_actions` | 1 | R | List the allowlisted process actions available to process_run, with their exact commands. | — |
| `process_run` | 4 | W | Run an allowlisted development command (pytest, npm build/test/install, rojo, git status/log) inside the workspace. No shell, no arbitrary arguments. Level 4: requires confirm=true. | `action`, `path`?, `timeoutMs`?, `confirm`? |
| `system_self_test` | 1 | R | Run a real end-to-end self test: invokes core tools for real and reports per-tool pass/fail. Use to verify the installation actually works. | — |

---

`?` = paramètre optionnel. Les schémas JSON complets sont exposés par MCP (`tools/list`)
et visibles dans le dashboard → MCP Explorer.
