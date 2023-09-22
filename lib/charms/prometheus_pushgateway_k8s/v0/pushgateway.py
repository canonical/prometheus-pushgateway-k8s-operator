# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details

r"""Interface library for the Prometheus Pushgateway.

This library wraps a relation endpoint using the `pushgwateway` interface
and exposes an API for forwarding metrics to Prometheus.


# Getting Started

## Provider side of the relation

This side of the relation is to be used by Prometheus Pushgateway Charm or any other charm that
provides the same service.

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.prometheus_pushgateway_k8s.v0.pushgateway
```

In the `metadata.yaml` of the charm, add the following:

```yaml
provides:
  push-endpoint:
    interface: pushgateway
```

In the source of your charm, first import the interface:

```
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayProvider
````

Instantiate the object in your charm's `__init__`, like so:

```
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayRequirer
from ops.charm import CharmBase

class PrometheusPushgatewayK8SOperatorCharm(CharmBase):
    def __init__(...):
        ...
        self.pushgateway_provider = PrometheusPushgatewayProvider(
            self, "push-endpoint", self._endpoint
        )
```

The relation name when instantiating PrometheusPushgatewayProvider defaults to `push-endpoint`,
you can pass a different one if used other name in `metadata.yaml`.


## Requierer side of the relation

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.prometheus_pushgateway_k8s.v0.pushgateway
```

In the `metadata.yaml` of the charm, add the following:

```yaml
requires:
  pushgateway:
    interface: pushgateway
```

In the source of your charm, first import the interface:

```
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayRequirer
````

Instantiate the object in your charm's `__init__`, like so:

```
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayRequirer
from ops.charm import CharmBase

class MyCharm(CharmBase):
    def __init__(...):
        ...
        self.pushgateway_requirer = PrometheusPushgatewayRequirer(self)
```

The relation name when instantiating PrometheusPushgatewayRequirer defaults to `pushgateway`,
you can pass a different one if used other name in `metadata.yaml`.

At any moment you can use the Pushgateway Requirer to send a metric (validating that the requirer
is ready), passing its name and value:

```
    if self.pushgateway_requirer.is_ready():
        self.pushgateway_requirer.send_metric("test_metric", 3.141592)
```

The requirer is ready when the relation to the Prometheus Pushgateway is properly established.

The `send_metric` call will just end quietly if the metric was sent succesfully, or will raise
an exception if something is wrong (that error should be logged or informed to the operator).
"""

import json
import logging
import ssl
from typing import Optional, Union
from urllib import request
from urllib.error import HTTPError

from ops.charm import CharmBase, RelationEvent
from ops.framework import Object

logger = logging.getLogger(__name__)


# The unique Charmhub library identifier, never change it
LIBID = "a0065690fe484ef296d5847fcbf1d728"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2

# the key in the relation data
RELATION_KEY = "push-endpoint"


class PrometheusPushgatewayProvider(Object):
    """Provider side for the Prometheus Pushgateway.

    This class is to be used by the Prometheus Pushgateway charm, please use
    the PrometheusPushgatewayRequirer class if you're bulding a charm and want to
    use this library to integrate with the Prometheus Pushgateway.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = "push-endpoint",
        endpoint: str = "http://127.0.0.1:9091",
    ):
        """Construct the interface for the Prometheus Pushgateway Provider side of the relation.

        Args:
            charm: a `CharmBase` object that manages this object. Typically,
                this is `self` in the instantiating class.
            relation_name: the name of the relation (whatever was used
                in the `requires` section in `metadata.yaml` for the `pushgateway` interface.
            endpoint: the endpoint that Prometheus Pushgateway expose to consumers, for instance:
                "https://pushgateway-0.pushgateway-endpoints.clite.svc.cluster.local:9091" or
                "http://10.1.38.86:9091"
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self.app = charm.app
        self.endpoint = endpoint
        events = charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_changed)
        self.framework.observe(events.relation_changed, self._on_relation_changed)

    def _on_relation_changed(self, event: RelationEvent):
        """Send the push endpoint info."""
        relation_data = event.relation.data[self.app]
        relation_data[RELATION_KEY] = json.dumps({"url": self.endpoint})

    def update_endpoint(self, endpoint: str):
        """Update endpoint in relation data."""
        self.endpoint = endpoint

        for rel in self._charm.model.relations.get(self._relation_name, []):
            if not rel:
                continue
            rel.data[self._charm.app][RELATION_KEY] = json.dumps({"url": self.endpoint})


class PrometheusPushgatewayRequirer(Object):
    """Requirer side for the Prometheus Pushgateway."""

    def __init__(self, charm: CharmBase, relation_name: str = "pushgateway"):
        """Construct the interface for the Prometheus Pushgateway.

        Args:
            charm: a `CharmBase` object that manages this object. Typically,
                this is `self` in the instantiating class.
            relation_name: the name of the relation (whatever was used
                in the `requires` section in `metadata.yaml` for
                the `pushgateway` interface.
        """
        super().__init__(charm, relation_name)
        self._relation_name = relation_name

    @property
    def _pushgateway_url(self) -> Optional[str]:
        """Build the pushgateway url using the relation data (if present, else return None)."""
        relation = self.model.get_relation(self._relation_name)
        if relation is None:
            logger.warning(
                "Prometheus Pushgateway Requirer not ready: "
                "charm not related to the Pushgateway service"
            )
            return None
        raw_data = relation.data[relation.app].get(RELATION_KEY)
        if raw_data is None:
            logger.warning(
                "Prometheus Pushgateway Requirer not ready: still no data in the relation"
            )
            return None
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning(
                "Prometheus Pushgateway Requirer not ready: corrupt data in the relation"
            )
            return None
        try:
            url = data["url"]
        except KeyError:
            logger.warning(
                "Prometheus Pushgateway Requirer not ready: "
                "missing mandatory keys in relation data"
            )
            return None
        return url

    def is_ready(self):
        """Return if the service is ready to send metrics."""
        return self._pushgateway_url is not None

    def send_metric(
        self,
        name: str,
        value: Union[float, int],
        ignore_error: bool = False,
        verify_ssl: bool = True,
        job_name: str = "default",
    ):
        """Send a metric to the Pushgateway.

        Args:
            name: the name of the metric.
            value: the value of the metric.
            ignore_error: raise or not error while performing the request.
            verify_ssl: verify ssl certificate in the request.
            job_name: name of the job for the current metric.
        """
        # This currently follows the "simple API" for the case of one metric
        # without labels, as indicated here:
        #    https://github.com/prometheus/pushgateway#api
        # TODO: support the more complex cases

        pushgateway_url = self._pushgateway_url
        if pushgateway_url is None:
            raise ValueError("The service is not ready.")
        if not isinstance(name, str) or not name.isascii() or not name:
            raise ValueError("The name must be a non-empty ASCII string.")
        if not isinstance(value, (float, int)):
            raise ValueError("The metric value must be an integer or float number.")

        payload = f"{name} {value}\n".encode("ascii")
        post_url = f"{pushgateway_url}metrics/job/{job_name}"
        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        try:
            request.urlopen(post_url, data=payload, context=ctx)
        except HTTPError:
            if not ignore_error:
                raise
