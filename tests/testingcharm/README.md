# testingcharm

Charm to support the testing of the Prometheus Pushgateway charm and its library.


## How to use it

Pack and deploy it:

```
charmcraft pack
juju deploy ./testingcharm_ubuntu-22.04-amd64.charm
```

It should be left in "blocked" state, waiting for the proper relation.

Relate it with the Pushgateway:

```
juju relate pushgateway-k8s testingcharm
```

Now it should be "active".

Use its action to send a metric to the Pushgateway:

```
juju run testingcharm/0 send-metric name=some_metric value="'3.42'"
```
