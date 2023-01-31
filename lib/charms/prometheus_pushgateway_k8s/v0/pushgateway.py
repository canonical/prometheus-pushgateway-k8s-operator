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

When your charm is deployed but the relation is still not added to the Prometheus Pushgateway
the metrics could not be sent.

For robustness the charm should only send metrics only after the `pushgateway_available` event
is received.

The following is a bare charm that holds a flag for when the Pushgateway is available, which is
set to True when the mentioned event arrives:

```
class ExampleCharm(CharmBase):

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(pushgateway_available=False)

        self.ppi = PrometheusPushgatewayInterface(self)
        self.framework.observe(self.ppi.on.pushgateway_available, self._on_pushgateway_available)

    def _on_pushgateway_available(self, _):
        self._stored.pushgateway_available = True
```
"""

import json
import logging
from typing import Union

import requests
from ops.charm import CharmBase, HookEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents, StoredState

logger = logging.getLogger(__name__)


# The unique Charmhub library identifier, never change it
LIBID = "a0065690fe484ef296d5847fcbf1d728"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = ["requests"]


class _PushgatewayAvailableEvent(EventBase):
    """Event emitted when the Prometheus Pushgateway is available to receive metrics."""


class _Events(ObjectEvents):
    """Events for the interface."""

    pushgateway_available = EventSource(_PushgatewayAvailableEvent)


class PrometheusPushgatewayInterface(Object):
    """Interface for the Prometheus Pushgateway."""

    _stored = StoredState()
    on = _Events()

    def __init__(self, charm: CharmBase):
        """Construct the interface for the Prometheus Pushgateway.

        Args:
            charm: a `CharmBase` object that manages this
                `MetricsEndpointProvider` object. Typically, this is
                `self` in the instantiating class.
        """
        super().__init__(charm, None)
        self._stored.set_default(pushgateway_url=None)

        self.framework.observe(charm.on.pushgateway_relation_created, self._on_push_relation)
        self.framework.observe(charm.on.pushgateway_relation_changed, self._on_push_relation)

    def _on_push_relation(self, event: HookEvent) -> None:
        """Receive the push endpoint information."""
        raw = event.relation.data[event.app].get("push-endpoint")
        if raw is not None:
            logger.info("Received push endpoint information: %r", raw)
            info = json.loads(raw)
            self._stored.pushgateway_url = "http://{hostname}:{port}/".format_map(info)
            self.on.pushgateway_available.emit()

    def send_metric(self, name: str, value: Union[float, int]):
        """Send a metric to the Pushgateway."""
        if not isinstance(name, str) or not name.isascii() or not name:
            raise ValueError("The name must be a non-empty ASCII string.")
        if not isinstance(value, (float, int)):
            raise ValueError("The metric value must be an integer or float number.")

        payload = f"{name} {value}\n".encode("ascii")
        post_url = self._stored.pushgateway_url + "metrics/job/testjob"

        resp = requests.post(post_url, data=payload)
        resp.raise_for_status()
