# Copyright 2022 Canonical
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

import ops.testing
from charm import PrometheusPushgatewayK8SOperatorCharm
from ops.model import ActiveStatus
from ops.testing import Harness

ops.testing.SIMULATE_CAN_CONNECT = True

VERSION_OUTPUT = """
pushgateway, version 1.5.1 (branch: HEAD, revision: 7afc96cfc3b20e56968ff30eea22b70e)
  build user:       root@fc81889ee1a6
  build date:       20221129-16:30:38
  go version:       go1.19.3
  platform:         linux/amd64
"""


class TestCharm(unittest.TestCase):
    def setUp(self, *_):
        self.container_name: str = "pushgateway"
        self.harness = Harness(PrometheusPushgatewayK8SOperatorCharm)
        self.harness.handle_exec(
            "pushgateway", ["/bin/pushgateway", "--version"], result=VERSION_OUTPUT
        )
        self.harness.begin()

    def test_pebble_ready_ok(self):
        expected_plan = {
            "services": {
                "pushgateway": {
                    "override": "replace",
                    "summary": "pushgateway process",
                    "command": "/bin/sh -c '/bin/pushgateway --persistence.file=/data/metrics 2>&1 | tee /var/log/pushgateway.log'",
                    "startup": "enabled",
                }
            },
        }

        self.harness.container_pebble_ready("pushgateway")
        updated_plan = self.harness.get_container_pebble_plan("pushgateway").to_dict()
        self.assertDictEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("pushgateway").get_service("pushgateway")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
