#!/usr/bin/env python3

# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju Charmed Operator for Prometheus Pushgateway."""

import logging
import socket
from typing import Any, Dict, List, Optional

import yaml
from charms.observability_libs.v0.cert_handler import CertHandler
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.prometheus_pushgateway_k8s.v0.pushgateway import PrometheusPushgatewayProvider
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, OpenedPort, WaitingStatus
from ops.pebble import Layer
from parse import search  # type: ignore

# By default, Pushgateway does not persist metrics, but we can specify a file in which
# the pushed metrics will be persisted (so that they survive restarts of the Pushgateway)
METRICS_PATH = "/data/metrics"

PUSHGATEWAY_DIR = "/etc/pushgateway"
PUSHGATEWAY_BINARY = "/bin/pushgateway"

KEY_PATH = f"{PUSHGATEWAY_DIR}/server.key"
CERT_PATH = f"{PUSHGATEWAY_DIR}/server.cert"
CA_CERT_PATH = f"{PUSHGATEWAY_DIR}/cos-ca.crt"
CA_CERT_TRUSTED_PATH = "/usr/local/share/ca-certificates/cos-ca.crt"
WEB_CONFIG_PATH = f"{PUSHGATEWAY_DIR}/web-config.yml"

logger = logging.getLogger(__name__)


class PrometheusPushgatewayK8SOperatorCharm(CharmBase):
    """A Juju Charmed Operator for Prometheus Pushgateway."""

    _name = "pushgateway"
    _http_listen_port = 9091
    _instance_addr = "127.0.0.1"

    def __init__(self, *args):
        super().__init__(*args)
        self._container = self.unit.get_container(self._name)
        self._set_ports()

        self.pushgateway_provider = PrometheusPushgatewayProvider(
            self, "push-endpoint", self._endpoint
        )

        # Provide ability for Pushgateway to be scraped by Prometheus using prometheus_scrape
        self._scraping = MetricsEndpointProvider(
            self,
            relation_name="metrics-endpoint",
            jobs=self._self_metrics_jobs,
            refresh_event=[
                self.on.update_status,
            ],
        )

        self._cert_handler = CertHandler(
            charm=self,
            key="pushgateway-server-cert",
            peer_relation_name="pushgateway-peers",
            extra_sans_dns=[self._hostname],
        )

        self.framework.observe(self._cert_handler.on.cert_changed, self._on_server_cert_changed)
        self.framework.observe(self.on.pushgateway_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.update_status, self._on_update_status)

    @property
    def _hostname(self) -> str:
        return socket.getfqdn()

    @property
    def _endpoint(self) -> str:
        scheme = "https" if self._tls_ready else "http"
        return f"{scheme}://{self._hostname}:{self._http_listen_port}/"

    @property
    def _command(self) -> str:
        args = [f"--persistence.file={METRICS_PATH}"]

        if self._web_config:
            args.append(f"--web.config.file={WEB_CONFIG_PATH}")

        command = [PUSHGATEWAY_BINARY] + args
        return " ".join(command)

    @property
    def _web_config(self) -> Optional[dict]:
        """Return the web.config.file contents as a dict, if TLS is enabled; otherwise None.

        Ref: https://prometheus.io/docs/prometheus/latest/configuration/https/
        """
        if self._tls_ready:
            return {
                "tls_server_config": {
                    "cert_file": CERT_PATH,
                    "key_file": KEY_PATH,
                }
            }
        return None

    @property
    def _service_version(self) -> Optional[str]:
        if not self._container.can_connect():
            return None

        version_output, _ = self._container.exec([PUSHGATEWAY_BINARY, "--version"]).wait_output()
        # Output looks like this:
        # pushgateway, version 1.5.1 (branch: HEAD, revision: 7afc96cfc3b20e56968ff30eea22b70e)
        #   build user:       root@fc81889ee1a6
        #   build date:       20221129-16:30:38
        #   go version:       go1.19.3
        #   platform:         linux/amd64

        # For some reason `/bin/pushgateway --version` is returning the result to stderr
        # instead of stdout.
        # `.wait_output()` return tuple of (stdout, stderr):
        #
        # (Pdb) self._container.exec(["/bin/pushgateway", "--version"]).wait_output()
        # ('', 'pushgateway, version 1.6.0 (....'"
        #
        # That is why we have this workaround here:
        version_output = _ if _ else version_output
        result = search("pushgateway, version {} ", version_output)

        if result is None:
            return result

        return result[0]

    @property
    def _certs_available(self) -> bool:
        return (
            self._cert_handler.enabled
            and self._cert_handler.cert
            and self._cert_handler.key
            and self._cert_handler.ca
        )

    @property
    def _tls_ready(self) -> bool:
        return (
            self._container.can_connect()
            and self._container.exists(CERT_PATH)
            and self._container.exists(KEY_PATH)
            and self._container.exists(CA_CERT_PATH)
        )

    @property
    def _self_metrics_jobs(self) -> List[Dict[str, Any]]:
        job: Dict[str, Any] = {
            "static_configs": [{"targets": [f"{self._hostname}:{self._http_listen_port}"]}]
        }

        if self._tls_ready:
            job["scheme"] = "https"

        return [job]

    def _on_server_cert_changed(self, _) -> None:
        self._update_certs()
        self._scraping.update_scrape_job_spec(self._self_metrics_jobs)
        self.pushgateway_provider.update_endpoint(self._endpoint)
        self._configure()

    def _on_pebble_ready(self, _) -> None:
        self._configure()

    def _on_config_changed(self, _) -> None:
        self._configure()

    def _on_stop(self, _) -> None:
        self.unit.set_workload_version("")

    def _on_upgrade_charm(self, _) -> None:
        self._configure()

    def _on_update_status(self, _) -> None:
        self._configure()

    def _configure(self) -> None:
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        self._set_service_version()
        self._handle_web_config()

        if self._set_pebble_layer():
            self._container.restart(self._name)
            logger.info("Prometheus Pushgateway (re)started")

        self.unit.status = ActiveStatus()

    def _handle_web_config(self) -> None:
        if web_config := self._web_config:
            self._container.push(
                WEB_CONFIG_PATH, yaml.safe_dump(web_config), make_dirs=True, encoding="utf-8"
            )
        else:
            self._container.remove_path(WEB_CONFIG_PATH, recursive=True)

    def _update_certs(self) -> None:
        if not self._container.can_connect():
            return

        certs = {
            CERT_PATH: self._cert_handler.cert,
            KEY_PATH: self._cert_handler.key,
            CA_CERT_PATH: self._cert_handler.ca,
            CA_CERT_TRUSTED_PATH: self._cert_handler.ca,
        }

        if self._certs_available:
            # Save the workload certificates
            for f, content in certs.items():
                self._container.push(
                    f,
                    content,
                    make_dirs=True,
                )
        else:
            for f in certs:
                self._container.remove_path(f, recursive=True)

        self._container.exec(["update-ca-certificates", "--fresh"]).wait()

    def _set_service_version(self) -> bool:
        """Set the service version in the unit."""
        version = self._service_version

        if version is None:
            logger.debug(
                "Cannot set workload version at this time: "
                "could not get Prometheus Pushgateway version."
            )
            return False

        self.unit.set_workload_version(version)
        return True

    def _set_pebble_layer(self) -> bool:
        """Set Pebble layer.

        Returns: True if Pebble layer was added, otherwise False.
        """
        current_layer = self._container.get_plan()
        new_layer = self._build_pebble_layer()

        if "services" not in current_layer.to_dict() or (
            current_layer.services != new_layer.services
        ):
            self._container.add_layer(self._name, new_layer, combine=True)
            return True

        return False

    def _build_pebble_layer(self) -> Layer:
        """Build the pebble layer structure."""
        return Layer(
            {
                "summary": "prometheus pushgateway layer",
                "description": "pebble config layer for prometheus pushgateway",
                "services": {
                    "pushgateway": {
                        "override": "replace",
                        "summary": "pushgateway process",
                        "command": self._command,
                        "startup": "enabled",
                    }
                },
            }
        )

    def _set_ports(self) -> None:
        """Open necessary (and close no longer needed) workload ports."""
        planned_ports = {
            OpenedPort("tcp", self._http_listen_port),
        }
        actual_ports = self.unit.opened_ports()

        # Ports may change across an upgrade, so need to sync
        ports_to_close = actual_ports.difference(planned_ports)
        for p in ports_to_close:
            self.unit.close_port(p.protocol, p.port)

        new_ports_to_open = planned_ports.difference(actual_ports)
        for p in new_ports_to_open:
            self.unit.open_port(p.protocol, p.port)


if __name__ == "__main__":  # pragma: nocover
    main(PrometheusPushgatewayK8SOperatorCharm)
