# Copyright 2023 Canonical
# See LICENSE file for licensing details.

"""Tests for the pushgateway.py charm library."""

import io
import json
from unittest.mock import patch
from urllib import response
from urllib.error import HTTPError

import pytest
from ops.testing import Harness

from src.charm import PrometheusPushgatewayK8SOperatorCharm
from tests.testingcharm.src.charm import TestingcharmCharm

TEST_URL = "http://hostname.test:9876/"


@pytest.fixture()
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


@pytest.fixture()
def related_requirer(testcharm_harness):
    """Provide an usefully related Prometheus Pushgateway Requirer."""
    payload = {"push-endpoint": json.dumps({"url": TEST_URL})}
    relation_id = testcharm_harness.add_relation("pushgateway", "remote")
    testcharm_harness.update_relation_data(relation_id, "remote", payload)
    return testcharm_harness.charm.pushgateway_requirer


@patch("socket.getfqdn", lambda: "testhost")
def test_provider_relation(pushgateway_harness):
    """Send connection information when the relation is created."""
    provider = pushgateway_harness.charm.pushgateway_provider
    relation_id = pushgateway_harness.add_relation("push-endpoint", "remote")
    data = pushgateway_harness.get_relation_data(relation_id, "prometheus-pushgateway-k8s")
    assert json.loads(data["push-endpoint"]) == {"url": f"http://testhost:{provider.port}/"}


def test_requirer_pushgateway_init(testcharm_harness):
    """The pushgateway is not ready on bootstrap."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    assert not requirer.is_ready()


def test_requirer_pushgateway_relation_changed_empty(testcharm_harness):
    """The pushgateway is not ready when the relation is established without data."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    testcharm_harness.add_relation("pushgateway", "remote")
    assert not requirer.is_ready()


def test_requirer_pushgateway_relation_changed_with_data(testcharm_harness):
    """The pushgateway is ready when the relation is established and has data."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    payload = {"push-endpoint": json.dumps({"url": TEST_URL})}

    relation_id = testcharm_harness.add_relation("pushgateway", "remote")
    testcharm_harness.update_relation_data(relation_id, "remote", payload)
    assert requirer.is_ready()
    assert requirer._pushgateway_url == TEST_URL


@pytest.mark.parametrize(
    "payload_content",
    [
        "this is not json",  # corrupt
        json.dumps({"foo": "bar"}),  # missing url
    ],
)
def test_requirer_pushgateway_relation_changed_bad_data(testcharm_harness, payload_content):
    """The pushgateway is not ready even if the relation has data, but corrupt or missing."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    payload = {"push-endpoint": payload_content}

    relation_id = testcharm_harness.add_relation("pushgateway", "remote")
    testcharm_harness.update_relation_data(relation_id, "remote", payload)
    assert not requirer.is_ready()


def test_requirer_pushgateway_relation_broken(testcharm_harness):
    """The pushgateway url is cleared if the relation disappears."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    payload = {"push-endpoint": json.dumps({"url": TEST_URL})}
    relation_id = testcharm_harness.add_relation("pushgateway", "remote")
    testcharm_harness.update_relation_data(relation_id, "remote", payload)
    assert requirer.is_ready()

    testcharm_harness.remove_relation(relation_id)
    assert not requirer.is_ready()


def test_requirer_sendmetric_not_ready(testcharm_harness):
    """Validate that the requirer is ready."""
    requirer = testcharm_harness.charm.pushgateway_requirer
    with pytest.raises(ValueError):
        requirer.send_metric("testmetric", 3.21)


@pytest.mark.parametrize(
    "name",
    [
        "moño",  # not ascii
        123,  # not a string
        "",  # empty
    ],
)
def test_requirer_sendmetric_bad_name_input(related_requirer, name):
    """Validate the name input to ensure the URL is properly built."""
    with pytest.raises(ValueError) as cm:
        related_requirer.send_metric(name, 3.21)
    assert str(cm.value) == "The name must be a non-empty ASCII string."


@pytest.mark.parametrize(
    "value",
    [
        "a string",  # not a number
        (4 + 5j),  # only scalar values
    ],
)
def test_requirer_sendmetric_bad_value_input(related_requirer, value):
    """Validate the value input to ensure the URL is properly built."""
    with pytest.raises(ValueError) as cm:
        related_requirer.send_metric("testmetric", value)
    assert str(cm.value) == "The metric value must be an integer or float number."


@pytest.mark.parametrize(
    "name, value, expected_body",
    [
        ("testmetric", 3.14, b"testmetric 3.14\n"),
        ("testmetric", 314, b"testmetric 314\n"),
        ("test_metric", 3.14, b"test_metric 3.14\n"),
    ],
)
def test_requirer_sendmetric_ok(related_requirer, name, value, expected_body):
    """The metric was sent ok."""
    expected_url = TEST_URL + "metrics/job/testjob"
    fake_resp = response.addinfourl(io.BytesIO(), {}, expected_url, code=200)
    with patch("urllib.request.urlopen", return_value=fake_resp) as mock_urlopen:
        related_requirer.send_metric(name, value)
    mock_urlopen.assert_called_with(expected_url, data=expected_body)


def test_requirer_sendmetric_error_raised(related_requirer):
    """Error raised because the metric was not sent ok."""
    expected_url = TEST_URL + "metrics/job/testjob"
    fake_error = HTTPError(expected_url, 400, "BAD REQUEST", {}, io.BytesIO())
    with patch("urllib.request.urlopen", side_effect=fake_error):
        with pytest.raises(HTTPError):
            related_requirer.send_metric("testmetric", 3.14)


def test_requirer_sendmetric_error_ignored(related_requirer):
    """The metric was not sent ok but the error is ignored."""
    expected_url = TEST_URL + "metrics/job/testjob"
    fake_error = HTTPError(expected_url, 400, "BAD REQUEST", {}, io.BytesIO())
    with patch("urllib.request.urlopen", side_effect=fake_error):
        related_requirer.send_metric("testmetric", 3.14, ignore_error=True)
