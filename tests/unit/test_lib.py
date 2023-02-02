# Copyright 2023 Canonical
# See LICENSE file for licensing details.

"""Tests for the pushgateway.py charm library."""

import json
from unittest.mock import patch

import pytest
import requests
import responses
from ops.testing import Harness

from src.charm import PrometheusPushgatewayK8SOperatorCharm
from tests.testingcharm.src.charm import TestingcharmCharm


@pytest.fixture()
@patch("src.charm.KubernetesServicePatch", lambda x, y: None)
def pushgateway_harness():
    harness = Harness(PrometheusPushgatewayK8SOperatorCharm)
    harness.begin()
    harness.set_leader()
    return harness


@pytest.fixture()
def testcharm_harness():
    harness = Harness(TestingcharmCharm)
    harness.begin()
    return harness


@patch("socket.getfqdn", lambda: "testhost")
def test_provider_relation(pushgateway_harness):
    """Send connection information when the relation is created."""
    provider = pushgateway_harness.charm.provider
    relation_id = pushgateway_harness.add_relation("push-endpoint", "remote")
    data = pushgateway_harness.get_relation_data(relation_id, "prometheus-pushgateway-k8s")
    assert json.loads(data["push-endpoint"]) == {"hostname": "testhost", "port": provider.port}


def test_requirer_pushgateway_url_default(testcharm_harness):
    """The pushgateway url has a default value."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    assert requirer._stored.pushgateway_url is None


def test_requirer_pushgateway_relation_changed_empty(testcharm_harness):
    """No changes when the relation is established without data."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    testcharm_harness.add_relation("pushgateway", "remote")
    assert requirer._stored.pushgateway_url is None
    assert not requirer.is_ready


def test_requirer_pushgateway_relation_changed_with_data(testcharm_harness):
    """The pushgateway url is set when the relation is established and has data."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    payload = {"push-endpoint": json.dumps({"port": "9876", "hostname": "hostname.test"})}

    relation_id = testcharm_harness.add_relation("pushgateway", "remote")
    testcharm_harness.update_relation_data(relation_id, "remote", payload)
    assert requirer._stored.pushgateway_url == "http://hostname.test:9876/"
    assert requirer.is_ready


def test_requirer_pushgateway_relation_broken(testcharm_harness):
    """The pushgateway url is cleared if the relation disappears."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    payload = {"push-endpoint": json.dumps({"port": "9876", "hostname": "hostname.test"})}
    relation_id = testcharm_harness.add_relation("pushgateway", "remote")
    testcharm_harness.update_relation_data(relation_id, "remote", payload)
    assert requirer.is_ready

    testcharm_harness.remove_relation(relation_id)
    assert not requirer.is_ready


@pytest.mark.parametrize(
    "name",
    [
        "moño",  # not ascii
        123,  # not a number
        "",  # empty
    ],
)
@responses.activate
def test_requirer_sendmetric_bad_name_input(testcharm_harness, name):
    """Validate the name input to ensure the URL is properly built."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    requirer._stored.pushgateway_url = "http://testhost:8080/"
    with pytest.raises(ValueError) as cm:
        requirer.send_metric(name, 3.21)
    assert str(cm.value) == "The name must be a non-empty ASCII string."


@pytest.mark.parametrize(
    "value",
    [
        "a string",  # not a number
        (4 + 5j),  # only scalar values
    ],
)
@responses.activate
def test_requirer_sendmetric_bad_value_input(testcharm_harness, value):
    """Validate the value input to ensure the URL is properly built."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    requirer._stored.pushgateway_url = "http://testhost:8080/"
    with pytest.raises(ValueError) as cm:
        requirer.send_metric("testmetric", value)
    assert str(cm.value) == "The metric value must be an integer or float number."


@pytest.mark.parametrize(
    "name, value, expected_body",
    [
        ("testmetric", 3.14, b"testmetric 3.14\n"),
        ("testmetric", 314, b"testmetric 314\n"),
        ("test_metric", 3.14, b"test_metric 3.14\n"),
    ],
)
@responses.activate
def test_requirer_sendmetric_ok(testcharm_harness, name, value, expected_body):
    """The metric was sent ok."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    requirer._stored.pushgateway_url = "http://testhost:8080/"
    responses.post(
        url="http://testhost:8080/metrics/job/testjob",
    )
    requirer.send_metric(name, value)
    assert responses.calls[0].request.body == expected_body


@responses.activate
def test_requirer_sendmetric_error_raised(testcharm_harness):
    """Error raised because the metric was not sent ok."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    requirer._stored.pushgateway_url = "http://testhost:8080/"
    responses.post(
        url="http://testhost:8080/metrics/job/testjob",
        status=400,
    )
    with pytest.raises(requests.exceptions.HTTPError):
        requirer.send_metric("testmetric", 3.14)


@responses.activate
def test_requirer_sendmetric_error_ignored(testcharm_harness):
    """The metric was not sent ok but the error is ignored."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    requirer._stored.pushgateway_url = "http://testhost:8080/"
    responses.post(
        url="http://testhost:8080/metrics/job/testjob",
        status=400,
    )
    requirer.send_metric("testmetric", 3.14, ignore_error=True)
