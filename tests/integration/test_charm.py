# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pushgateway_charm: Path):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    assert ops_test.model
    image = METADATA["resources"]["pushgateway-image"]["upstream-source"]
    resources = {"pushgateway-image": image}

    # Deploy the charm and wait for active/idle status
    await asyncio.gather(
        ops_test.model.deploy(pushgateway_charm, resources=resources, application_name=APP_NAME),
        ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=1000
        ),
    )
