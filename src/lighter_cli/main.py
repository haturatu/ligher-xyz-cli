"""Console entry point.

Command parsing, dispatch, signing and presentation deliberately live outside
this module so importing the console script has no application policy.
"""
from .commands.app import *  # noqa: F403 - backwards-compatible library surface
from .commands.app import main

__all__ = ["main"]
