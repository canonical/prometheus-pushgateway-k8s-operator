# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details

r"""Interface library for the Prometheus Pushgateway.

This library wraps the relation endpoint using the `pushgwateway` interface
and provides a Python API for sending metrics.


## Getting Started

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.prometheus_pushgateway_k8s/v0/pushgateway
```

In the `metadata.yaml` of the charm, add the following:

```yaml
requires:
  pushgateway:
    interface: pushgateway
```

In the source of your charm, first import the interface:

```
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayInterface
````

Just instantiate the object in `__init__` and then use it when desired to send a metric, passing
its name and value:

```
self.ppi = PrometheusPushgatewayInterface(self)
...
self.ppi.send_metric("test_metric", 3.141592)
```

The `send_metric` call will just end quietly if the metric was sent succesfully, or will raise
an exception if something is wrong (that error should be logged or informed to the operator).


## Waiting for Pushgateway

When your charm is deployed but the relation is still not added to the Prometheus Pushgateway,
metrics cannot not be sent.

For robustness you should only send metrics when the interface is ready:

```
self.ppi = PrometheusPushgatewayInterface(self)
...
if self.ppi.is_ready():
    self.ppi.send_metric("test_metric", 3.141592)
```
"""

import json
import logging
from typing import Union

import requests
from ops.charm import CharmBase, HookEvent
from ops.framework import Object, StoredState

logger = logging.getLogger(__name__)


# The unique Charmhub library identifier, never change it
LIBID = "a0065690fe484ef296d5847fcbf1d728"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = ["requests"]


class PrometheusPushgatewayInterface(Object):
    """Interface for the Prometheus Pushgateway."""

    _stored = StoredState()

    def __init__(self, charm: CharmBase):
        """Construct the interface for the Prometheus Pushgateway.

        Args:
            charm: a `CharmBase` object that manages this
                `MetricsEndpointProvider` object. Typically, this is
                `self` in the instantiating class.
        """
        super().__init__(charm, None)
        self._stored.set_default(pushgateway_url=None)

        self.framework.observe(
            charm.on.pushgateway_relation_created, self._on_push_relation_changed
        )
        self.framework.observe(
            charm.on.pushgateway_relation_changed, self._on_push_relation_changed
        )
        self.framework.observe(
            charm.on.pushgateway_relation_broken, self._on_push_relation_removed
        )

    @property
    def is_ready(self):
        """Return if the service is ready to send metrics."""
        return self._stored.pushgateway_url is not None

    def _on_push_relation_changed(self, event: HookEvent) -> None:
        """Receive the push endpoint information."""
        raw = event.relation.data[event.app].get("push-endpoint")
        if raw is not None:
            logger.info("Received push endpoint information: %r", raw)
            info = json.loads(raw)
            self._stored.pushgateway_url = "http://{hostname}:{port}/".format_map(info)

    def _on_push_relation_removed(self, event: HookEvent) -> None:
        """Clear the push endpoint information."""
        self._stored.pushgateway_url = None

    def send_metric(self, name: str, value: Union[float, int], ignore_error: bool = False):
        """Send a metric to the Pushgateway."""
        if not isinstance(name, str) or not name.isascii() or not name:
            raise ValueError("The name must be a non-empty ASCII string.")
        if not isinstance(value, (float, int)):
            raise ValueError("The metric value must be an integer or float number.")

        payload = f"{name} {value}\n".encode("ascii")
        post_url = self._stored.pushgateway_url + "metrics/job/testjob"

        resp = requests.post(post_url, data=payload)
        if not ignore_error:
            resp.raise_for_status()
