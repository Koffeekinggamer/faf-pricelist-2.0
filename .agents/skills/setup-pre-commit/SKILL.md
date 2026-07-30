---
name: setup-pre-commit
description: Set up Husky pre-commit hooks with lint-staged (Prettier), Ruff for Python, and tests in the current repo. Use when user wants to add pre-commit hooks, set up Husky, configure lint-staged, or add commit-time formatting/testing.
---

# Setup Pre-Commit Hooks

## FAF Price Book overlay

This repo is **Python / Streamlit**, not a TypeScript app.

- **Do not** add `npm run typecheck` — there is no JS/TS typecheck.
- Pre-commit runs: `npx lint-staged` then `npm test` (pytest via `.venv`).
- lint-staged: Ruff on `*.py` via `scripts/run_ruff.sh` (`.venv/bin/ruff`, else PATH), Prettier on other text.
- `package.json` is **hooks-only**.

If `npx skills update` restores the upstream JS-oriented text, re-apply this FAF overlay.

## What This Sets Up

- **Husky** pre-commit hook
- **lint-staged** running Prettier on staged non-Python text + Ruff on `*.py`
- **Prettier** config (if missing)
- **test** script in the pre-commit hook (pytest) — **no typecheck**

## Steps

### 1. Detect package manager

Check for `package-lock.json` (npm), `pnpm-lock.yaml` (pnpm), `yarn.lock` (yarn), `bun.lockb` (bun). Use whichever is present. Default to npm if unclear.

### 2. Install dependencies

Install as devDependencies:

```
husky lint-staged prettier
```

Also ensure the Python venv has `ruff` and `pytest` (`pip install -r requirements.txt`).

### 3. Initialize Husky

```bash
npx husky init
```

This creates `.husky/` dir and adds `prepare: "husky"` to package.json.

### 4. Create `.husky/pre-commit`

Write this file (no shebang needed for Husky v9+):

```
npx lint-staged
npm test
```

**FAF:** omit `typecheck`. Replace `npm` with detected package manager if needed. Keep `test` pointing at `.venv/bin/python -m pytest -q`.

### 5. Create `.lintstagedrc`

```json
{
  "*.py": [
    "scripts/run_ruff.sh check --fix",
    "scripts/run_ruff.sh format"
  ],
  "*": "prettier --ignore-unknown --write"
}
```

Provide `scripts/run_ruff.sh` that prefers `.venv/bin/ruff` then falls back to `ruff` on PATH.

### 6. Create `.prettierrc` (if missing)

Only create if no Prettier config exists. Use these defaults:

```json
{
  "useTabs": false,
  "tabWidth": 2,
  "printWidth": 80,
  "singleQuote": false,
  "trailingComma": "es5",
  "semi": true,
  "arrowParens": "always"
}
```

### 7. Verify

- [ ] `.husky/pre-commit` exists and is executable
- [ ] `.lintstagedrc` exists
- [ ] `prepare` script in package.json is `"husky"`
- [ ] `prettier` config exists
- [ ] No `typecheck` line in the pre-commit hook
- [ ] Run `npx lint-staged` to verify it works
- [ ] Run `npm test` (pytest)

### 8. Commit

Stage all changed/created files and commit with message: `Add pre-commit hooks (husky + lint-staged + prettier)`

This will run through the new pre-commit hooks — a good smoke test that everything works.

## Notes

- Husky v9+ doesn't need shebangs in hook files
- `prettier --ignore-unknown` skips files Prettier can't parse (images, etc.)
- The pre-commit runs lint-staged first (fast, staged-only), then full tests — **not** typecheck
