"""Opt-in real integration. Sends GET only, never upload/start/control.

PRINTLAB_LIVE_TEST=1 python -m pytest tests/test_live_readonly.py
"""
import os
import pytest
from printlab import bambuddy


@pytest.mark.skipif(os.environ.get("PRINTLAB_LIVE_TEST") != "1", reason="Live integration requires explicit test opt-in")
def test_bambuddy_inventory_readonly_connection():
    client = bambuddy.Client(write=False)
    try:
        rows = client.get("inventory/spools")
        assert isinstance(rows, list)
        assert bambuddy.inventory()["state"] == "online"
    finally:
        client.close()
