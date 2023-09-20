# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import List

import aiohttp

logger = logging.getLogger(__name__)


class Prometheus:
    """Utility to get information from a Prometheus service."""

    def __init__(self, host: str, scheme: str = "http"):
        self.base_url = f"{scheme}://{host}:9090"

    async def is_ready(self) -> bool:
        """Send a GET request to check readiness."""
        url = f"{self.base_url}/-/ready"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=False) as response:
                return response.status == 200

    async def labels(self) -> List[str]:
        """Send a GET request to get labels."""
        url = f"{self.base_url}/api/v1/label/__name__/values"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=False) as response:
                result = await response.json()
        return result["data"] if result["status"] == "success" else []
