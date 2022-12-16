# Prometheus Pushgateway Charmed Operator for K8s

## Description

This charmed operator automates the operational procedures of running the Prometheus Pushgateway, a service that allows ephemeral and batch jobs to expose their metrics to Prometheus.

## About persistence

By default, Pushgateway does not persist metrics. 

However, the service is started with the `--persistence.file=/data/metrics` parameter, so it will persist the metrics there (so that they survive restarts of the Pushgateway).
