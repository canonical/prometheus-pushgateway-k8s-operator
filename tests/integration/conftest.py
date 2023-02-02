# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
from datetime import datetime
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

store = {}


def timed_memoizer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        fname = func.__qualname__
        logger.info("Started: %s" % fname)
        start_time = datetime.now()
        if fname in store:
            ret = store[fname]
        else:
            logger.info("Return for {} not cached".format(fname))
            ret = await func(*args, **kwargs)
            store[fname] = ret
        logger.info("Finished: {} in {} seconds".format(fname, datetime.now() - start_time))
        return ret

    return wrapper


@pytest.fixture(scope="module")
@timed_memoizer
async def pushgateway_charm(ops_test: OpsTest) -> Path:
    """Prometheus Pushgateway charm used for integration testing."""
    charm = await ops_test.build_charm(".")
    return charm


@pytest.fixture(scope="module")
@timed_memoizer
async def tester_charm(ops_test: OpsTest) -> Path:
    """A charm to integration test the Pushgateway charm."""
    charm = await ops_test.build_charm("tests/testingcharm")
    return charm
