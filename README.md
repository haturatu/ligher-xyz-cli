# Lighter CLI

`lighter-cli` is a scriptable command-line client for the [Lighter API](https://apidocs.lighter.xyz/docs/get-started). It uses the official [lighter-python](https://github.com/elliottech/lighter-python) SDK for transaction signing, nonce management, API authentication, and WebSocket connectivity.

## Install

```bash
cd lighter-cli
python -m pip install -e .
lighter --help
```

## Configure an account

Create an API key in Lighter first. The `account_index` and `api_key_index` are Lighter integer identifiers; API key indices 2–254 are intended for API use.

```bash
lighter account add main 12345 2
# Prefer an environment variable so the private key is never stored on disk:
export LIGHTER_API_PRIVATE_KEY='...'
lighter account portfolio
```

The config is stored at `~/.config/lighter-cli/config.json` with owner-only permissions. `LIGHTER_CONFIG` changes that location. `--testnet` selects `https://testnet.zklighter.elliot.ai`.

User-facing help is localized. Select a language explicitly with `--lang` or
set `LIGHTER_LANG`; English and Japanese are currently bundled.

```bash
lighter --lang ja --help
LIGHTER_LANG=en lighter --help
```

## Commands

```bash
lighter markets ls
lighter asset book ETH
lighter account orders
lighter order limit buy 0.01 ETH 2500
lighter order market sell 0.01 ETH
lighter order cancel 1234 --coin ETH
lighter order cancel-all --coin ETH
lighter order set-leverage ETH 5 --isolated
```

The default terminal output is concise and table-oriented. Use `--json` only when an automation needs the original API response.

```bash
lighter --testnet markets ls
lighter --testnet markets ls --perp-only
lighter --testnet asset price ETH
lighter --testnet asset book ETH
lighter --testnet account balances --user 1
lighter --testnet account positions --user 1
lighter --testnet account portfolio --user 1
```

Prices and sizes are converted using the market-specific decimal precision returned by `orderBookDetails`. Market orders require a worst acceptable price, as required by Lighter.

Global options must appear before the command, for example `lighter --testnet markets ls`.

## Security

Use `LIGHTER_API_PRIVATE_KEY` rather than `--api-private-key` when possible. The CLI never prints configured private keys. Signed actions require the official `lighter-sdk`, including its platform signer library.

## Layout

The package uses a `src/` layout. `src/lighter_cli/commands/` holds command-family presentation, `client/` holds transport adapters, `lib/` holds formatting helpers, `cli/` owns terminal rendering, and `i18n/` owns language selection and translations. The SDK remains the only source of transaction signing and WebSocket protocol behavior.
