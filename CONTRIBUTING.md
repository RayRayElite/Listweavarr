# Contributing to Listweavarr

Start with [CODE_MAP](docs/CODE_MAP.md). It explains what each module owns, where to find a workflow, and why safety checks exist. You do not need to understand the whole app to fix one adapter or UI component.

## First contribution

1. Fork and clone the repository; create a small branch for one behavior change.
2. Run `python app.py`. Configure your own test connections through Settings. Never commit `data/`, `.env`, API keys, real provider responses or private screenshots.
3. Find the feature in the code map. Trace the browser event ? API route ? feature module ? response ? renderer.
4. Add a regression test for meaningful behavior. Unit tests mock network/services and never require your NAS. Prefer synthetic fixtures over copied websites or artwork.
5. Run the commands in README, then inspect the changed UI at desktop and phone sizes when relevant.
6. Open a pull request describing the problem, resulting behavior and checks run. Keep unrelated formatting, renames and feature work separate.

## How to write helpful code

- Explain intent and non-obvious constraints. A useful comment says why an exact ID is required or why an update is staged, rather than restating a loop.
- Use plain names, small helpers and module boundaries. Add a docstring when introducing a public function or workflow entry point.
- Add a labelled section or update CODE_MAP when introducing a subsystem. Keep user-facing copy free of internal implementation details.
- The backend currently uses a flat set of focused modules next to app.py. This is intentional: it preserves a dependency-free startup and easy test imports. Scripts, tests, web assets and documentation have their own folders.
- Frontend scripts are loaded in order from web/index.html. Shared globals are existing architecture; do not silently change callback names or move scripts without checking the Node harness and browser routes.

## Service boundaries

Use provider IDs, not similar titles, to establish ownership or relationships. Preserve separate movie/show/season/episode scopes. Validate imported data before saving it. Unknown availability is not confirmed missing. Recommendations are not evidence of franchise canon.

A preview must not acquire media, publish a list, send Discord messages or overwrite Plex. Mutating remote actions belong behind explicit review, with failures leaving a recoverable result. Use isolated mocks for those paths.

State mutations use app.LOCK and atomic save_state. Read network data outside the lock where possible; compare revisions before applying slow results. Keep caches and credentials in the configured data directory. Runtime configuration belongs in runtime_config.py.

## Version control and releases

Commit understandable steps and push your branch regularly. CI runs Python, client, release-hygiene and real Docker persistence checks. Maintainers tag a release only after those checks pass. Revert a bad commit with `git revert`; do not force-push shared history. Back up your data separately: Git deliberately does not contain it.

By submitting code you agree to license it under AGPL-3.0-only and confirm you have the right to contribute it. Do not submit third-party posters, logos, full website captures or credentials. Be respectful, explain tradeoffs and welcome contributors with different experience levels.
