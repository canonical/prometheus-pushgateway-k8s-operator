# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path
from typing import List

import aiohttp
import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CHARMLIB_PATH = Path("lib") / "charms" / "prometheus_pushgateway_k8s" / "v0" / "pushgateway.py"


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


@pytest.mark.abort_on_fail
async def test_prometheus_integration(
    ops_test: OpsTest,
    pushgateway_charm: Path,
    tester_charm: Path,
):
    """Validate the integration between the Pushgateway and Prometheous."""
    prometheus_app_name = "prometheus"
    tester_name = "testingcharm"
    apps = [APP_NAME, prometheus_app_name, tester_name]

    image = METADATA["resources"]["pushgateway-image"]["upstream-source"]
    resources = {"pushgateway-image": image}

    await asyncio.gather(
        ops_test.model.deploy(
            pushgateway_charm,
            resources=resources,
            application_name=APP_NAME,
        ),
        ops_test.model.deploy(
            "prometheus-k8s",
            application_name=prometheus_app_name,
            channel="stable",
            trust=True,
        ),
        ops_test.model.deploy(
            tester_charm,
            application_name=tester_name,
        ),
    )
    logger.info("All services deployed")

    # wait for all charms to be active
    # related to the pushgateway charm
    await ops_test.model.wait_for_idle(apps=apps, status="active", wait_for_exact_units=1)
    logger.info("All services active")

    # prepare the Prometheus helper and check it's ready
    status = await ops_test.model.get_status()
    app = status["applications"][prometheus_app_name]
    host = app["units"][f"{prometheus_app_name}/0"]["address"]
    prometheus = Prometheus(host)
    assert await prometheus.is_ready()
    logger.info("Prometheus ready")

    await asyncio.gather(
        ops_test.model.add_relation(
            f"{APP_NAME}:metrics-endpoint", f"{prometheus_app_name}:metrics-endpoint"
        ),
        ops_test.model.add_relation(f"{tester_name}:pushgateway", f"{APP_NAME}:push-endpoint"),
    )
    logger.info("Relations issued")

    await ops_test.model.wait_for_idle(apps=apps, status="active")
    logger.info("All services related")

    # run the action to push a metric
    tester_unit = ops_test.model.applications[tester_name].units[0]
    test_metric = "some_testing_metric"
    action = await tester_unit.run_action("send-metric", name=test_metric, value="3.14")
    result = (await action.wait()).results
    assert result["ok"] == "True", result
    logger.info("Metric sent to the Pushgateway")

    for i in range(20):
        labels = await prometheus.labels()
        if test_metric in labels:
            logger.info("Metric shown in Prometheus")
            break
        await asyncio.sleep(5)
    else:
        pytest.fail("Metric didn't get to Prometheus")


@pytest.mark.abort_on_fail
async def test_prometheus_ca_integration(
    ops_test: OpsTest,
    pushgateway_charm: Path,
    tester_charm: Path,
):
    """Validate the integration between the Pushgateway and Prometheous."""
    prometheus_app_name = "prometheus"
    tester_name = "testingcharm"
    ca_name = "ca"
    apps = [APP_NAME, prometheus_app_name, tester_name, ca_name]

    image = METADATA["resources"]["pushgateway-image"]["upstream-source"]
    resources = {"pushgateway-image": image}

    await asyncio.gather(
        ops_test.model.deploy(
            pushgateway_charm,
            resources=resources,
            application_name=APP_NAME,
        ),
        ops_test.model.deploy(
            "prometheus-k8s",
            application_name=prometheus_app_name,
            channel="edge",
            trust=True,
        ),
        ops_test.model.deploy(
            "self-signed-certificates",
            application_name=ca_name,
            channel="edge",
            trust=True,
        ),
        ops_test.model.deploy(
            tester_charm,
            application_name=tester_name,
        ),
    )
    logger.info("All services deployed")

    # wait for all charms to be active
    # related to the pushgateway charm
    await ops_test.model.wait_for_idle(apps=apps, status="active", wait_for_exact_units=1)
    logger.info("All services active")

    # prepare the Prometheus helper and check it's ready
    status = await ops_test.model.get_status()
    app = status["applications"][prometheus_app_name]
    host = app["units"][f"{prometheus_app_name}/0"]["address"]
    prometheus = Prometheus(host)
    assert await prometheus.is_ready()
    logger.info("Prometheus ready")

    await asyncio.gather(
        ops_test.model.add_relation(
            f"{APP_NAME}:metrics-endpoint", f"{prometheus_app_name}:metrics-endpoint"
        ),
        ops_test.model.add_relation(APP_NAME, ca_name),
        ops_test.model.add_relation(prometheus_app_name, ca_name),
        ops_test.model.add_relation(f"{tester_name}:pushgateway", f"{APP_NAME}:push-endpoint"),
    )
    logger.info("Relations issued")
    await asyncio.sleep(100)
    await ops_test.model.wait_for_idle(apps=apps, status="active")
    logger.info("All services related")

    # run the action to push a metric
    tester_unit = ops_test.model.applications[tester_name].units[0]

    test_metric = "some_testing_metric"
    action = await tester_unit.run_action("send-metric", name=test_metric, value="3.14")
    result = (await action.wait()).results
    assert result["ok"] == "True", result
    logger.info("Metric sent to the Pushgateway")

    await asyncio.sleep(100)
    prometheus = Prometheus(host, scheme="https")
    labels = await prometheus.labels()

    if test_metric in labels:
        logger.info("Metric shown in Prometheus")
    else:
        pytest.fail("Metric didn't get to Prometheus")
