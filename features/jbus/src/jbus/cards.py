"""The address of a page of jbus view (`view_address`), and of an item's page (`view_link`)."""

from __future__ import annotations

import os

VIEW_PORT = 4388


def view_address(page: str) -> str:
    """Return the address of a page of jbus view, `page` being its path and its fragment, such as
    `/#/demo`. The page is at the first origin in `JBUS_VIEW_ORIGINS`, which is the proxy in front
    of the view. Without such an origin, the page is at the first name in `JBUS_VIEW_NAMES`, then
    at the address in `JBUS_VIEW_HOST`, and last at 127.0.0.1, at the view's port."""
    origins = [one.strip() for one in os.environ.get("JBUS_VIEW_ORIGINS", "").split(",")]
    origin = next((one for one in origins if one), "")
    if origin:
        return origin.rstrip("/") + page
    names = [one.strip() for one in os.environ.get("JBUS_VIEW_NAMES", "").split(",")]
    host = next((one for one in names if one), os.environ.get("JBUS_VIEW_HOST") or "127.0.0.1")
    return f"http://{host}:{VIEW_PORT}{page}"


def view_link(project: str, name: str) -> str:
    """Return the item's page in jbus view (`view_address`)."""
    return view_address(f"/#/{project}/item/{name}")
