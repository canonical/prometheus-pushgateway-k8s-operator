#!/usr/bin/env python3
# Copyright 2023 Facundo Batista
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Pushgateway Integration Test Charm.

A charm to test integration with the Prometheus Pushgateway charm. It just integrates
with the Prometheus Pushgateway charm and provides an action to send metrics there.
"""

import logging

from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayRequirer
from ops.charm import ActionEvent, CharmBase
from ops.main import main
from ops.model import ActiveStatus

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class TestingcharmCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.send_metric_action, self._on_send_metric)

        self.pushgateway_requirer = PrometheusPushgatewayRequirer(self)

    def _on_install(self, _) -> None:
        """Installed."""
        self.unit.status = ActiveStatus()

    def _on_send_metric(self, event: ActionEvent) -> None:
        if not self.pushgateway_requirer.is_ready():
            event.fail("The Prometheus Pushgateway service is not currently available.")
            return

        name = event.params["name"].strip()
        if " " in name:
            event.fail("The metric name cannot contain spaces.")
            return
        try:
            value = float(event.params["value"])
        except ValueError:
            event.fail("The metric value must be a float.")
            return

        if not name.isascii():
            event.fail("The metric name must be ASCII.")
            return

        try:
            self.pushgateway_requirer.send_metric(name, value, verify_ssl=False)
        except Exception as exc:
            event.set_results({"ok": False, "error": str(exc)})
        else:
            event.set_results({"ok": True})


if __name__ == "__main__":  # pragma: nocover
    main(TestingcharmCharm)
