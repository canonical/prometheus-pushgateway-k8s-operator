# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helpers to deploy a monolithic Tempo stack and query ingested traces.

jubilant/sync; kept separate from the OpsTest/async ``helpers.py``.
"""

from typing import List, Set, cast

import jubilant
import requests
from jubilant import Juju

TEMPO = "tempo"
TEMPO_WORKER = "tempo-worker"
# An app named "s3" collides with Kubernetes' S3_PORT env var, which seaweedfs's `weed`
# binary tries to parse as a flag and crashes on. Use any other name.
S3_APP = "s3-app"
# Tempo's current builds are on the `dev` track.
TEMPO_CHANNEL = "dev/edge"


def deploy_monolithic_tempo_cluster(juju: Juju) -> None:
    """Deploy a monolithic Tempo cluster: coordinator + worker + a seaweedfs S3 backend."""
    juju.deploy("tempo-coordinator-k8s", app=TEMPO, channel=TEMPO_CHANNEL, trust=True)
    juju.deploy("tempo-worker-k8s", app=TEMPO_WORKER, channel=TEMPO_CHANNEL, trust=True)
    juju.deploy("seaweedfs-k8s", app=S3_APP, channel="latest/edge")

    juju.integrate(TEMPO, TEMPO_WORKER)
    juju.integrate(f"{TEMPO}:s3", S3_APP)

    juju.wait(
        lambda status: jubilant.all_active(status, TEMPO, TEMPO_WORKER, S3_APP),
        error=jubilant.any_error,
        timeout=1000,
    )


def get_app_ip_address(juju: Juju, app_name: str) -> str:
    """Return a juju application's IP address from ``juju status``."""
    return juju.status().apps[app_name].address


def get_ingested_traces_tag_values(tempo_host: str, tag: str, tls: bool = False) -> Set[str]:
    """Return every value Tempo has seen for a tag (e.g. ``service.name``)."""
    scheme = "https" if tls else "http"
    url = f"{scheme}://{tempo_host}:3200/api/search/tag/{tag}/values"
    resp = requests.get(url, verify=False, timeout=10)
    resp.raise_for_status()
    return set(cast(List[str], resp.json()["tagValues"]))
