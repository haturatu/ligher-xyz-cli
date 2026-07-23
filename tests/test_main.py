import argparse

import pytest

from lighter_cli import main
from lighter_cli.commands import app
from lighter_cli.infra import account_repo


def test_root_help_is_localized(capsys):
    with pytest.raises(SystemExit):
        main.main(["--lang", "en", "--help"])
    assert "Lighter DEX CLI" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main.main(["--lang", "ja", "--help"])
    assert "Lighter DEX のCLI" in capsys.readouterr().out
from lighter_cli.cli.output import render


def test_integer_exact_precision():
    assert main.integer("12.34", 2, "size") == 1234
    with pytest.raises(SystemExit):
        main.integer("12.345", 2, "size")


def test_account_configuration_lifecycle(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main, "CONFIG_PATH", tmp_path / "config.json")
    main.main(["account", "add", "test", "101", "2"])
    main.main(["account", "set-default", "test"])
    capsys.readouterr()
    main.main(["account", "ls"])
    rendered = capsys.readouterr().out
    assert "test" in rendered
    assert "101" in rendered


def test_numeric_market_uses_metadata(monkeypatch):
    args = argparse.Namespace(testnet=True, url=None)
    monkeypatch.setattr(app, "order_book_details", lambda _: [{"market_id": 9, "symbol": "X", "supported_size_decimals": 3}])
    assert main.market(args, "9")["symbol"] == "X"


def test_human_output_is_a_table_and_json_is_opt_in():
    rows = [{"market": "ETH", "price": "2000"}]
    assert "market" in render(rows)
    assert "ETH" in render(rows)
    assert render(rows, json_mode=True).startswith("[")


def test_accounts_are_network_scoped_and_private_values_are_encrypted(tmp_path, monkeypatch):
    path = tmp_path / "accounts.json"
    monkeypatch.setattr(account_repo, "CONFIG_PATH", path)
    account_repo.save_accounts(False, {"main": {"account_index": 1, "api_key_index": 2, "api_private_key": "secret"}}, "main")
    account_repo.save_accounts(True, {"test": {"account_index": 3, "api_key_index": 4, "auth_token": "token"}}, "test")
    assert "secret" not in path.read_text()
    assert account_repo.list_accounts(False)[0]["main"]["api_private_key"] == "secret"
    assert account_repo.list_accounts(True)[0]["test"]["auth_token"] == "token"


def test_hl_compatible_order_shapes():
    args = argparse.Namespace(a="BTC", b="60000", c=None, stake=50.0)
    assert main.limit_shape(args, main.die) == ("0", "BTC", "60000")
    args = argparse.Namespace(a="BTC", b=None, stake=50.0)
    assert main.market_shape(args, main.die) == ("0", "BTC")
