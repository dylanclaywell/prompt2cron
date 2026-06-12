# prompt2cron

A small CustomTkinter desktop app that converts a plain-English schedule into a
crontab expression using Claude — and converts it back the other way so you can
verify it.

- **Forward:** "every weekday at 9am" → `0 9 * * 1-5` (via Claude)
- **Reverse:** the cron field is editable, and a live natural-language
  description (via [`cron-descriptor`](https://pypi.org/project/cron-descriptor/))
  updates as you type — so you can confirm Claude's output, tweak it, or write
  your own schedule from scratch.

## Setup

This project uses [uv](https://docs.astral.sh/uv/).

```sh
# from the project root
uv sync
```

### Set your Anthropic API key

Either configure it **in the app** — `Settings → Anthropic API Key…` — which
saves it securely to your **OS credential store** (Windows Credential Manager,
macOS Keychain, or the Linux Secret Service) via
[`keyring`](https://pypi.org/project/keyring/), or set the environment variable:

```sh
# PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# bash / zsh
export ANTHROPIC_API_KEY="sk-ant-..."
```

A key saved via Settings takes precedence over the environment variable.

## Run

```sh
uv run prompt2cron
# or
uv run python -m prompt2cron.app
```

## Build a standalone .exe

PyInstaller is included as a dev dependency. From the project root:

```sh
uv run pyinstaller prompt2cron.spec --noconfirm --clean
```

The result is a `dist/prompt2cron/` folder (~46 MB) containing
`prompt2cron.exe` and its `_internal/` dependencies — ship the whole folder,
launch `prompt2cron.exe`, no Python required. The spec force-collects
CustomTkinter's theme assets, `keyring`'s OS backends, and `certifi`'s CA bundle
so the frozen app works standalone. The API key still lives in the OS keychain,
so a packaged build picks up a key you saved while running from source.

## How it works

| Direction | Engine | Notes |
|-----------|--------|-------|
| English → cron | Claude (`claude-opus-4-8`) via the Anthropic SDK | Uses structured outputs so the model returns a clean 5-field expression plus a one-line explanation. |
| cron → English | `cron-descriptor` (local, no network) | Runs on every keystroke in the cron field; invalid expressions are flagged inline. |

Cron expressions are standard 5-field (`minute hour day-of-month month day-of-week`).
