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

from ops.charm import ActionEvent, CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayInterface

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class TestingcharmCharm(CharmBase):

    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(pushgateway_available=False)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.send_metric_action, self._on_send_metric)

        self.ppi = PrometheusPushgatewayInterface(self)
        self.framework.observe(self.ppi.on.pushgateway_available, self._on_pushgateway_available)

    def _on_install(self, _) -> None:
        """Installed, needs the relation."""
        self.unit.status = BlockedStatus("needs the relation with the pushgateway")

    def _on_pushgateway_available(self, _) -> None:
        """Flag the Pushgateway as available."""
        self._stored.pushgateway_available = True
        self.unit.status = ActiveStatus()

    def _on_send_metric(self, event: ActionEvent) -> None:
        if not self._stored.pushgateway_available:
            event.fail("The Prometheus Pushgateway service is not yet available.")
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
            self.ppi.send_metric(name, value)
        except Exception as exc:
            event.set_results({"ok": False, "error": str(exc)})
        else:
            event.set_results({"ok": True})


if __name__ == "__main__":  # pragma: nocover
    main(TestingcharmCharm)
