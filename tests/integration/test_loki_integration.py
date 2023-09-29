# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import Loki
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CHARMLIB_PATH = Path("lib") / "charms" / "prometheus_pushgateway_k8s" / "v0" / "pushgateway.py"


@pytest.mark.abort_on_fail
async def test_loki_integration(
    ops_test: OpsTest,
    pushgateway_charm: Path,
):
    """Validate the integration between the Pushgateway and Loki."""
    loki_app_name = "loki"
    apps = [APP_NAME, loki_app_name]

    image = METADATA["resources"]["pushgateway-image"]["upstream-source"]
    resources = {"pushgateway-image": image}

    await asyncio.gather(
        ops_test.model.deploy(
            pushgateway_charm,
            resources=resources,
            application_name=APP_NAME,
        ),
        ops_test.model.deploy(
            "loki-k8s",
            application_name=loki_app_name,
            channel="stable",
            trust=True,
        ),
    )
    logger.info("All services deployed")

    # wait for all charms to be active
    # related to the pushgateway charm
    await ops_test.model.wait_for_idle(apps=apps, status="active", wait_for_exact_units=1)
    logger.info("All services active")

    # prepare the Loki helper and check it's ready
    status = await ops_test.model.get_status()
    app = status["applications"][loki_app_name]
    host = app["units"][f"{loki_app_name}/0"]["address"]
    loki = Loki(host)
    logger.info("Loki ready")

    await asyncio.gather(
        ops_test.model.add_relation(f"{APP_NAME}:log-proxy", f"{loki_app_name}"),
    )
    logger.info("Relations issued")

    await ops_test.model.wait_for_idle(apps=apps, status="active")
    logger.info("All services related")

    await asyncio.sleep(10)
    result = await loki.query(query='{juju_charm="prometheus-pushgateway-k8s"} |= ``')
    assert result
