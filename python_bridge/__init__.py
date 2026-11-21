"""`python_bridge` — thin, documented entry point for the Studio Bridge.

The implementation lives in :mod:`omnibridge.studio_bridge` so it ships with the installed
OMNIBRIDGE package (tooling, tests, packaging). This package only exists so the component can
be launched exactly as the architecture describes::

    python -m python_bridge

Equivalent: ``python -m omnibridge.studio_bridge``.
"""
from omnibridge.studio_bridge import __version__
from omnibridge.studio_bridge.config import BridgeConfig, load_config
from omnibridge.studio_bridge.main import StudioBridge, main

__all__ = ["__version__", "BridgeConfig", "load_config", "StudioBridge", "main"]
