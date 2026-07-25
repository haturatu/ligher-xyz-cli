# Lighter CLI

Python CLI for [Lighter](https://lighter.xyz/) account management, market data,
and SDK-signed trading workflows. It uses the official
[lighter-python SDK](https://github.com/elliottech/lighter-python) for signing,
nonces, authentication, and WebSocket connectivity.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Shell completion](#shell-completion)
- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [Accounts and security](#accounts-and-security)
- [Output and languages](#output-and-languages)
- [Testnet](#testnet)
- [Development](#development)
- [Project layout](#project-layout)

## Requirements

- Python 3.10 or newer
- A Lighter account for private account data and trading
- An API key only for SDK-signed operations
- Optional: GNU `make` for development tasks and `msgfmt` for translations

## Installation

Install from this repository:

```bash
git clone https://github.com/haturatu/ligher-cli.git
cd ligher-cli/lighter-cli
python3 -m pip install --user -e .
lighter --help
```

For a development setup with local tooling:

```bash
make venv
source .venv/bin/activate
make check
```

`make install` installs the editable package and configures Bash completion.
This project intentionally does not build or publish a single-file binary.

## Shell completion

Enable completion in the current Bash session:

```bash
eval "$(lighter completion bash)"
```

Persist it in `~/.bashrc`:

```bash
echo 'eval "$(lighter completion bash)"' >> ~/.bashrc
```

`make uninstall` removes the package and the completion line managed by the
Makefile.

## Quick start

Public market data needs no account:

```bash
lighter markets ls
lighter markets search ETH
lighter asset price BTC
lighter asset book ETH
```

Create a named Lighter account profile. `account_index` and `api_key_index`
are integer values from Lighter; API key indices 2–254 are intended for API
use.

```bash
lighter account add main 12345 2
lighter account ls
lighter account set-default main
```

Keep the API private key in an environment variable whenever possible:

```bash
export LIGHTER_API_PRIVATE_KEY='your-api-private-key'
export LIGHTER_AUTH_TOKEN='optional-read-only-token'
lighter account balances
lighter account positions
```

## Command reference

```text
lighter [--json] [--testnet] [--lang LANG] <group> <command>

account    add | ls | set-default | remove | positions | orders | balances | portfolio
order      ls | limit | market | twap | tpsl | twap-cancel | cancel | cancel-all | set-leverage | configure
asset      price | book | leverage
markets    ls | search
referral   set | status
completion bash
```

### Global options

| Option | Description |
|---|---|
| `--json` | Emit the original Lighter API payload as JSON. |
| `--testnet` | Use `https://testnet.zklighter.elliot.ai` and the testnet account profile. |
| `--lang en` / `--lang ja` | Select user-facing language. English is the default. |

Global options must appear before the command:

```bash
lighter --testnet markets ls
lighter --lang ja account balances
```

### Accounts

```bash
lighter account add main 12345 2
lighter account ls
lighter account set-default main
lighter account remove main --force

lighter account balances
lighter account positions
lighter account portfolio
lighter account orders
lighter account balances --user 12345
```

Human-readable account views use Rich tables. Positions with zero size are
omitted. Use `--json` when an integration needs Lighter's unmodified account
payload.

### Markets and assets

```bash
lighter markets ls
lighter markets ls --perp-only --sort-by volume
lighter markets ls --spot-only
lighter markets search ETH
lighter markets search BTC --perp-only

lighter asset price BTC
lighter asset book ETH
lighter asset leverage BTC
```

`markets ls` renders a compact perpetual/spot overview. Sort keys are
`volume`, `oi`, `price`, `change`, `funding`, and `coin`.

### Orders

All numerical prices and sizes are converted using each market's precision
from Lighter's `orderBookDetails` endpoint.

```bash
# Limit: side size coin price
lighter order limit long 0.001 BTC 65000

# Stake form: side coin price --stake USD [--leverage N]
lighter order limit long BTC 65000 --stake 50 --leverage 10 --cross

# Market: side size coin
lighter order market short 0.1 ETH --slippage 0.5

# Stake form for market orders
lighter order market long BTC --stake 50 --leverage 10 --isolated

# Close part or all of an open position
lighter order market close ETH --ratio 0.5

# Native Lighter TWAP order. Comma-separated duration is accepted.
lighter order twap long 1 BTC 30
lighter order twap short 1 ETH 5,10

# Position protection and cancellation
lighter order tpsl BTC --tp 70000 --sl 60000
lighter order cancel 12345
lighter order cancel                 # choose from active orders
lighter order cancel-all --coin BTC --yes
lighter order set-leverage BTC 10 --cross
```

Lighter's SDK has no native randomized-TWAP parameter, so this CLI does not
offer Hyperliquid's `--randomize` option. `--stake` is a USD margin amount;
when leverage is set, the derived notional is `stake × leverage`.

Signed order methods return a signed transaction for inspection by default.
Keep private keys out of shell history and verify all transaction payloads
before submission workflows.

### Referral

```bash
lighter referral status
lighter referral set MYCODE
```

Referral endpoints require a configured account and authorization token.

## Accounts and security

Configuration defaults to:

```text
~/.config/lighter-cli/config.json
```

Override it with `LIGHTER_CONFIG`. Account profiles are separated by network:
the profile selected with `--testnet` is never used for mainnet.

The repository encrypts stored `api_private_key` and `auth_token` values with
ChaCha20. The encryption key is derived from the current command path and OS
user, or may be explicitly supplied with `LIGHTER_CONFIG_KEY` for a portable
configuration. This is local-at-rest protection, not a replacement for a
secret manager. Prefer `LIGHTER_API_PRIVATE_KEY` and `LIGHTER_AUTH_TOKEN` over
storing sensitive values in the profile.

Never commit API keys, auth tokens, or local configuration files.

## Output and languages

The default is English:

```bash
lighter account balances
```

Japanese can be selected per command or through `LIGHTER_LANG`:

```bash
lighter --lang ja account balances
LIGHTER_LANG=ja lighter markets ls
```

Translations use gettext catalogs under `src/lighter_cli/locale/`. Rebuild
compiled catalogs after editing a `.po` file:

```bash
make locales
```

## Testnet

Testnet changes both the endpoint and the selected account profile:

```bash
lighter --testnet markets ls
lighter --testnet account add test 101 2
lighter --testnet account balances --user 101
```

Use a testnet-only API key and account index. Do not reuse a mainnet secret in
test scripts.

## Development

```bash
make help
make locales
make test
make lint
make check
make package
```

`make check` compiles gettext catalogs, compile-checks source and tests, and
runs pytest. The repository currently uses a `src/` layout and package data
includes both `.po` and compiled `.mo` files.

## Project layout

```text
src/lighter_cli/
├── cli/        # terminal-oriented adapters
├── commands/   # command dispatch and presentation
├── core/       # runtime context and policy
├── client/     # REST transport adapter
├── infra/      # encrypted, network-scoped account repository
├── services/   # order input normalization and use cases
├── i18n/       # gettext installation and language resolution
├── locale/     # translation catalogs
└── main.py     # thin console entry point
```

## References

- [Lighter documentation](https://docs.lighter.xyz/)
- [Lighter API documentation](https://apidocs.lighter.xyz/docs/get-started)
- [Official Lighter Python SDK](https://github.com/elliottech/lighter-python)
