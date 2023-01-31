# Copyright 2023 Canonical
# See LICENSE file for licensing details.

"""Tests for the pushgateway.py charm library."""

import json
from unittest.mock import patch

import pytest
import requests
import responses
from ops.testing import Harness

from tests.testingcharm.src.charm import TestingcharmCharm


@pytest.fixture()
@patch("charm.KubernetesServicePatch", lambda x, y: None)
def harness():
    harness = Harness(TestingcharmCharm)
    harness.begin()
    return harness


def test_pushgateway_url_default(harness):
    """The pushgateway url has a default value."""
    ppi = harness.charm.ppi
    assert ppi._stored.pushgateway_url is None


def test_pushgateway_relation_empty(harness):
    """No changes when the relation is established without data."""
    ppi = harness.charm.ppi
    harness.add_relation("pushgateway", "remote")
    assert ppi._stored.pushgateway_url is None


def test_pushgateway_relation_with_data(harness):
    """The pushgateway is set when the relation is established and has data."""
    ppi = harness.charm.ppi
    payload = {"push-endpoint": json.dumps({"port": "9876", "hostname": "hostname.test"})}

    relation_id = harness.add_relation("pushgateway", "remote")
    harness.update_relation_data(relation_id, "remote", payload)
    assert ppi._stored.pushgateway_url == "http://hostname.test:9876/"


@pytest.mark.parametrize(
    "name",
    [
        "moño",  # not ascii
        123,  # not a number
        "",  # empty
    ],
)
@responses.activate
def test_sendmetric_bad_name_input(harness, name):
    """Validate the name input to ensure the URL is properly built."""
    ppi = harness.charm.ppi
    ppi._stored.pushgateway_url = "http://testhost:8080/"
    with pytest.raises(ValueError) as cm:
        ppi.send_metric(name, 3.21)
    assert str(cm.value) == "The name must be a non-empty ASCII string."


@pytest.mark.parametrize(
    "value",
    [
        "a string",  # not a number
        (4 + 5j),  # only scalar values
    ],
)
@responses.activate
def test_sendmetric_bad_value_input(harness, value):
    """Validate the value input to ensure the URL is properly built."""
    ppi = harness.charm.ppi
    ppi._stored.pushgateway_url = "http://testhost:8080/"
    with pytest.raises(ValueError) as cm:
        ppi.send_metric("testmetric", value)
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
def test_sendmetric_ok(harness, name, value, expected_body):
    """The metric was sent ok."""
    ppi = harness.charm.ppi
    ppi._stored.pushgateway_url = "http://testhost:8080/"
    responses.post(
        url="http://testhost:8080/metrics/job/testjob",
    )
    ppi.send_metric(name, value)
    assert responses.calls[0].request.body == expected_body


@responses.activate
def test_sendmetric_error(harness):
    """The metric was not sent ok."""
    ppi = harness.charm.ppi
    ppi._stored.pushgateway_url = "http://testhost:8080/"
    responses.post(
        url="http://testhost:8080/metrics/job/testjob",
        status=400,
    )
    with pytest.raises(requests.exceptions.HTTPError):
        ppi.send_metric("testmetric", 3.14)
