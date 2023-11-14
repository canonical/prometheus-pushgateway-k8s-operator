# Prometheus Pushgateway Charmed Operator for K8s

[![CharmHub Badge](https://charmhub.io/prometheus-pushgateway-k8s/badge.svg)](https://charmhub.io/prometheus-pushgateway-k8s)
[![Release Charm to Edge and Publish Libraries](https://github.com/canonical/prometheus-pushgateway-k8s-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/prometheus-pushgateway-k8s-operator/actions/workflows/release.yaml)
[![Discourse Status](https://img.shields.io/discourse/status?server=https%3A%2F%2Fdiscourse.charmhub.io&style=flat&label=CharmHub%20Discourse)](https://discourse.charmhub.io)

## Description

This charmed operator automates the operational procedures of running the Prometheus Pushgateway, a service that allows ephemeral and batch jobs to expose their metrics to Prometheus.

## About persistence

By default, Pushgateway does not persist metrics. 

However, the service is started with the `--persistence.file=/data/metrics` parameter, so it will persist the metrics there (so that they survive restarts of the Pushgateway).
