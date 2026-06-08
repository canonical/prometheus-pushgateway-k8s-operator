# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""End-to-end test that the charm's hook spans reach Tempo over `charm-tracing`.

Deploys the charm with a monolithic Tempo cluster, relates `charm-tracing`, and checks
the charm's spans show up in Tempo. Uses jubilant (the `juju` fixture comes from
pytest-jubilant).
"""

from __future__ import annotations

import pathlib

import jubilant
import pytest
import yaml
from tempo_helpers import (
    S3_APP,
    TEMPO,
    TEMPO_WORKER,
    deploy_monolithic_tempo_cluster,
    get_app_ip_address,
    get_ingested_traces_tag_values,
)
from tenacity import retry, stop_after_attempt, wait_fixed

METADATA = yaml.safe_load(pathlib.Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
RESOURCES = {
    "pushgateway-image": METADATA["resources"]["pushgateway-image"]["upstream-source"]
}


@pytest.mark.abort_on_fail
def test_deploy_charm_and_tempo(juju: jubilant.Juju, charm: pathlib.Path) -> None:
    """Deploy the charm and a monolithic Tempo cluster, then integrate charm-tracing."""
    # GIVEN this charm and a monolithic Tempo stack
    juju.deploy(charm, APP_NAME, resources=RESOURCES, trust=True)
    deploy_monolithic_tempo_cluster(juju)

    # WHEN the charm-tracing relation is established with Tempo
    juju.integrate(f"{APP_NAME}:charm-tracing", f"{TEMPO}:tracing")

    # THEN every application settles into active
    juju.wait(
        lambda status: jubilant.all_active(status, APP_NAME, TEMPO, TEMPO_WORKER, S3_APP),
        error=jubilant.any_error,
        timeout=1000,
    )


@retry(stop=stop_after_attempt(6), wait=wait_fixed(10))
def test_charm_traces_reach_tempo(juju: jubilant.Juju) -> None:
    """Assert that this charm's spans actually show up in Tempo."""
    # GIVEN update-status fires every 5s so a charm-tracing span is emitted quickly
    juju.model_config({"update-status-hook-interval": "5s"})

    # WHEN we query Tempo for the service names it has ingested
    services = get_ingested_traces_tag_values(get_app_ip_address(juju, TEMPO), tag="service.name")

    # THEN our charm appears among them
    assert APP_NAME in services, (
        f"expected {APP_NAME!r} in ingested services, got: {sorted(services)}"
    )
