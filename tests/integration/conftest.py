# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest


CHARMLIB_PATH = Path("lib/charms/prometheus_pushgateway_k8s/v0/pushgateway.py")

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
    testingcharm_path = Path("tests") / "testingcharm"

    dest_charmlib = testingcharm_path / CHARMLIB_PATH
    shutil.rmtree(dest_charmlib.parent, ignore_errors=True)
    dest_charmlib.parent.mkdir(parents=True)
    dest_charmlib.hardlink_to(CHARMLIB_PATH)

    clean_cmd = ["charmcraft", "clean", "-p", testingcharm_path]
    await ops_test.run(*clean_cmd)
    charm = await ops_test.build_charm(testingcharm_path)

    shutil.rmtree(dest_charmlib.parent)
    return charm
