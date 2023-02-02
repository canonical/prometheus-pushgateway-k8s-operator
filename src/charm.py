#!/usr/bin/env python3

# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju Charmed Operator for Prometheus Pushgateway."""

import logging
from typing import Optional

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayProvider
from ops.charm import CharmBase, HookEvent
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer
from parse import search  # type: ignore

# By default, Pushgateway does not persist metrics, but we can specify a file in which
# the pushed metrics will be persisted (so that they survive restarts of the Pushgateway)
METRICS_PATH = "/data/metrics"

logger = logging.getLogger(__name__)


class PrometheusPushgatewayK8SOperatorCharm(CharmBase):
    """A Juju Charmed Operator for Prometheus Pushgateway."""

    _name = "pushgateway"
    _http_listen_port = 9091
    _instance_addr = "127.0.0.1"

    def __init__(self, *args):
        super().__init__(*args)
        self._container = self.unit.get_container(self._name)

        self.service_patch = KubernetesServicePatch(
            self, [(self.app.name, self._http_listen_port, self._http_listen_port)]
        )
        self.provider = PrometheusPushgatewayProvider(
            self, "push-endpoint", self._http_listen_port
        )

        # Provide ability for Pushgateway to be scraped by Prometheus using prometheus_scrape
        self._scraping = MetricsEndpointProvider(
            self,
            relation_name="metrics-endpoint",
            jobs=[{"static_configs": [{"targets": [f"*:{self._http_listen_port}"]}]}],
        )

        self.framework.observe(self.on.pushgateway_pebble_ready, self._on_pebble_ready)

    def _on_pebble_ready(self, event: HookEvent) -> None:
        """Set version and configure."""
        self._set_service_version()

        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        restart_needed = self._set_pebble_layer()
        if restart_needed:
            self._container.restart(self._name)
            logger.info("Prometheus Pushgateway (re)started")

        self.unit.status = ActiveStatus()

    def _set_service_version(self) -> bool:
        """Set the service version in the unit."""
        version = self._get_service_version()

        if version is None:
            logger.debug(
                "Cannot set workload version at this time: "
                "could not get Prometheus Pushgateway version."
            )
            return False

        self.unit.set_workload_version(version)
        return True

    def _set_pebble_layer(self) -> bool:
        """Set Pebble layer.

        Returns: True if Pebble layer was added, otherwise False.
        """
        current_layer = self._container.get_plan()
        new_layer = self._build_pebble_layer()

        if "services" not in current_layer.to_dict() or (
            current_layer.services != new_layer.services
        ):
            self._container.add_layer(self._name, new_layer, combine=True)
            return True

        return False

    def _build_pebble_layer(self) -> Layer:
        """Build the pebble layer structure."""
        return Layer(
            {
                "summary": "prometheus pushgateway layer",
                "description": "pebble config layer for prometheus pushgateway",
                "services": {
                    "pushgateway": {
                        "override": "replace",
                        "summary": "pushgateway process",
                        "command": f"/bin/pushgateway --persistence.file={METRICS_PATH}",
                        "startup": "enabled",
                    }
                },
            }
        )

    def _get_service_version(self) -> Optional[str]:
        """Get the version of the running service."""
        if not self._container.can_connect():
            return None

        version_output, _ = self._container.exec(["/bin/pushgateway", "--version"]).wait_output()
        # Output looks like this:
        # pushgateway, version 1.5.1 (branch: HEAD, revision: 7afc96cfc3b20e56968ff30eea22b70e)
        #   build user:       root@fc81889ee1a6
        #   build date:       20221129-16:30:38
        #   go version:       go1.19.3
        #   platform:         linux/amd64
        result = search("pushgateway, version {} ", version_output)

        if result is None:
            return result

        return result[0]


if __name__ == "__main__":  # pragma: nocover
    main(PrometheusPushgatewayK8SOperatorCharm)
