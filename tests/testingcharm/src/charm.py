#!/usr/bin/env python3
# Copyright 2023 Facundo Batista
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Pushgateway Integration Test Charm.

A charm to test integration with the Prometheus Pushgateway charm. It just integrates
with the Prometheus Pushgateway charm and provides an action to send metrics there.
"""

import json
import logging

import requests

from ops.charm import CharmBase, ActionEvent, HookEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class TestingcharmCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(pushgateway_url=None)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.pushgateway_relation_created, self._on_push_relation)
        self.framework.observe(self.on.pushgateway_relation_changed, self._on_push_relation)
        self.framework.observe(self.on.send_metric_action, self._on_send_metric)

    def _on_install(self, _) -> None:
        """Installed, needs the relation."""
        self.unit.status = BlockedStatus("needs the relation with the pushgateway")

    def _on_push_relation(self, event: HookEvent) -> None:
        """Receive the push endpoint information."""
        raw = event.relation.data[event.app].get("push-endpoint")
        if raw is not None:
            logger.info("Received push endpoint information: %r", raw)
            info = json.loads(raw)
            self._stored.pushgateway_url = "http://{hostname}:{port}/".format_map(info)
            self.unit.status = ActiveStatus()

    def _on_send_metric(self, event: ActionEvent) -> None:
        if self._stored.pushgateway_url is None:
            event.fail("Testing charm not properly related to the Prometheus Pushgateway.")
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

        payload = f"{name} {value}\n"
        try:
            payload_bytes = payload.encode("ascii")
        except UnicodeEncodeError:
            event.fail("The metric name must be ASCII.")
            return

        post_url = self._stored.pushgateway_url + "metrics/job/testjob"
        resp = requests.post(post_url, data=payload_bytes)
        event.set_results({"status-code": str(resp.status_code), "content": resp.text})


if __name__ == "__main__":  # pragma: nocover
    main(TestingcharmCharm)
