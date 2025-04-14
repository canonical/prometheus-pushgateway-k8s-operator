from ops.testing import Container, Context, Exec, State

from charm import PUSHGATEWAY_BINARY, PrometheusPushgatewayK8SOperatorCharm


def test_parser():
    ctx = Context(PrometheusPushgatewayK8SOperatorCharm)

    mock_stdout = """
pushgateway, version 42.42.42 (branch: HEAD, revision: 7afc96cfc3b20e56968ff30eea22b70e)
  build user:       root@fc81889ee1a6
  build date:       20221129-16:30:38
  go version:       go1.19.3
  platform:         linux/amd64
""".strip()

    container = Container(
        "pushgateway",
        can_connect=True,
        execs={Exec((PUSHGATEWAY_BINARY, "--version"), return_code=0, stderr=mock_stdout)},
    )
    state_out = ctx.run(ctx.on.update_status(), state=State(containers=[container]))
    assert state_out.workload_version == "42.42.42"
