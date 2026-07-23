"""Runtime context shared by command families."""
from __future__ import annotations

from dataclasses import dataclass

MAINNET = "https://mainnet.zklighter.elliot.ai"
TESTNET = "https://testnet.zklighter.elliot.ai"


@dataclass(frozen=True)
class CLIContext:
    testnet: bool = False
    json_output: bool = False

    @property
    def endpoint(self) -> str:
        return TESTNET if self.testnet else MAINNET

    @property
    def network(self) -> str:
        return "testnet" if self.testnet else "mainnet"
