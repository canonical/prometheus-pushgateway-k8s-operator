# Copyright 2022 Canonical
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import PropertyMock, patch

import ops.testing
from ops.model import ActiveStatus, BlockedStatus, Container, WaitingStatus
from ops.pebble import ProtocolError
from ops.testing import Harness

from charm import PrometheusPushgatewayK8SOperatorCharm

ops.testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    @patch("lightkube.core.client.GenericSyncClient")
    def setUp(self, *_):
        self.container_name: str = "prometheus-pushgateway"
        self.harness = Harness(PrometheusPushgatewayK8SOperatorCharm)
        patcher = patch.object(
            PrometheusPushgatewayK8SOperatorCharm, "_get_service_version"
        )
        self.mock_version = patcher.start()
        self.mock_version.return_value = "2.4.0"
        self.addCleanup(patcher.stop)
        self.harness.begin()

    def test_pebble_ready_ok(self):
        expected_plan = {
            "services": {
                "pushgateway": {
                    "override": "replace",
                    "summary": "pushgateway process",
                    "command": f"/bin/pushgateway --persistence.file=/data/metrics",
                    "startup": "enabled",
                }
            },
        }

        self.harness.container_pebble_ready("pushgateway")
        updated_plan = self.harness.get_container_pebble_plan("pushgateway").to_dict()
        self.assertEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("pushgateway").get_service("pushgateway")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
