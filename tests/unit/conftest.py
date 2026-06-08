# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures for the scenario-based unit tests."""

import json

import pytest
from ops import testing

from charm import PrometheusPushgatewayK8SOperatorCharm

# `/bin/pushgateway --version` writes to stderr (see charm._service_version).
VERSION_EXEC = testing.Exec(
    command_prefix=["/bin/pushgateway", "--version"],
    stderr="pushgateway, version 1.11.0 (branch: HEAD, revision: 7afc96cfc3b20e56968ff30eea22)",
)


@pytest.fixture
def context():
    """A fresh scenario Context for the charm, loading metadata from charmcraft.yaml."""
    return testing.Context(PrometheusPushgatewayK8SOperatorCharm, charm_root=".")


@pytest.fixture
def container():
    """The pushgateway workload container with a stubbed --version exec."""
    return testing.Container("pushgateway", can_connect=True, execs={VERSION_EXEC})


@pytest.fixture
def charm_tracing_relation():
    """A charm-tracing relation pointing at a Tempo coordinator over HTTP."""
    return testing.Relation(
        endpoint="charm-tracing",
        interface="tracing",
        remote_app_name="tempo",
        remote_app_data={
            "receivers": json.dumps(
                [{"protocol": {"name": "otlp_http", "type": "http"}, "url": "http://tempo:4318"}]
            ),
        },
        remote_units_data={0: {}},
    )


@pytest.fixture
def tls_charm_tracing_relation():
    """A charm-tracing relation pointing at a Tempo coordinator over HTTPS."""
    return testing.Relation(
        endpoint="charm-tracing",
        interface="tracing",
        remote_app_name="tempo",
        remote_app_data={
            "receivers": json.dumps(
                [{"protocol": {"name": "otlp_http", "type": "http"}, "url": "https://tempo:4318"}]
            ),
        },
        remote_units_data={0: {}},
    )


@pytest.fixture
def ca_cert_relation():
    """A receive-ca-cert relation supplying a CA used to validate TLS to the tracing backend."""
    return testing.Relation(
        endpoint="receive-ca-cert",
        interface="certificate_transfer",
        remote_app_name="self-signed-certificates",
        remote_app_data={
            "ca": "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----",
        },
        remote_units_data={0: {}},
    )
