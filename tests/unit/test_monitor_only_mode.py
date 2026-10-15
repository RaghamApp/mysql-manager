from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY

from mysql_manager.cluster import ClusterManager
from mysql_manager.enums import MysqlClusterState, MysqlReplicationProblem
from mysql_manager.instance import Mysql


# methods that only read from mysql servers and etcd. in monitor-only mode nothing else
# may be called on them
MYSQL_READ_METHODS = {
    "ping",
    "get_replica_status",
    "find_replication_problems",
}
CLUSTER_DATA_READ_METHODS = {
    "get_cluster_state",
    "get_cluster_data",
    "get_mysqls",
    "get_users",
    "get_remote",
    "get_fail_interval",
    "is_cluster_data_available",
}


class StopRun(Exception):
    pass


def make_mysql(name: str, role: str) -> MagicMock:
    mysql = MagicMock(spec=Mysql)
    mysql.name = name
    mysql.host = name
    mysql.role = role
    mysql.user = "root"
    mysql.password = "root"
    mysql.health_check_failures = 0
    mysql.status = "up"
    return mysql


def called_methods(mock: MagicMock) -> set[str]:
    return {call[0].split(".")[0] for call in mock.method_calls}


def skipped_actions(action: str) -> float:
    return REGISTRY.get_sample_value(
        "mysql_manager_skipped_actions_total", {"action": action}
    ) or 0


@pytest.fixture
def monitor_only_cluster():
    mgr = ClusterManager.__new__(ClusterManager)
    mgr.monitor_only = True
    mgr.cluster_data_handler = MagicMock()
    mgr.cluster_data_handler.get_cluster_state.return_value = MysqlClusterState.CREATED.value
    mgr.etcd_client = MagicMock()
    mgr.fail_interval = 15
    mgr.users = {"replPassword": "password"}
    mgr.src = make_mysql("s1", "source")
    mgr.repl = make_mysql("s2", "replica")
    mgr.remote = None
    # this only writes a local file inside the mysql manager container
    mgr._write_cluster_state = MagicMock()
    return mgr


def assert_cluster_untouched(mgr: ClusterManager, *mysqls: MagicMock):
    for mysql in mysqls:
        assert called_methods(mysql) <= MYSQL_READ_METHODS, mysql.method_calls
    assert called_methods(mgr.cluster_data_handler) <= CLUSTER_DATA_READ_METHODS
    assert mgr.etcd_client.method_calls == []


def test_does_not_clone_replica_that_is_not_replicating(monitor_only_cluster):
    mgr = monitor_only_cluster
    mgr.repl.get_replica_status.return_value = None
    mgr.repl.find_replication_problems.return_value = [MysqlReplicationProblem.NOT_REPLICA.value]
    before = skipped_actions("join_replica_to_source")

    mgr.reconcile_cluster()

    assert_cluster_untouched(mgr, mgr.src, mgr.repl)
    assert skipped_actions("join_replica_to_source") == before + 1


def test_does_not_restart_stopped_replication(monitor_only_cluster):
    mgr = monitor_only_cluster
    mgr.repl.get_replica_status.return_value = {"Source_Host": "s1"}
    mgr.repl.find_replication_problems.return_value = [
        MysqlReplicationProblem.SQL_THREAD_NOT_RUNNING.value
    ]
    before = skipped_actions("restart_replication")

    mgr.reconcile_cluster()

    assert_cluster_untouched(mgr, mgr.src, mgr.repl)
    assert skipped_actions("restart_replication") == before + 1
    assert REGISTRY.get_sample_value(
        "mysql_replication_problem", {"host": "s2", "problem": "sql_thread_not_running"}
    ) == 1


def test_does_not_fail_over_when_source_is_down(monitor_only_cluster):
    mgr = monitor_only_cluster
    src, repl = mgr.src, mgr.repl
    src.ping.side_effect = Exception("connection refused")
    repl.get_replica_status.return_value = {"Source_Host": "s1"}
    repl.find_replication_problems.return_value = []
    before = skipped_actions("failover")

    for _ in range(mgr.master_failure_threshold + 2):
        mgr.reconcile_cluster()

    assert_cluster_untouched(mgr, src, repl)
    assert mgr.src is src and mgr.repl is repl
    assert skipped_actions("failover") > before


def test_does_not_run_initial_setup_on_new_cluster(monitor_only_cluster):
    mgr = monitor_only_cluster
    mgr.cluster_data_handler.get_cluster_state.return_value = MysqlClusterState.NEW.value

    mgr.start()

    assert_cluster_untouched(mgr, mgr.src, mgr.repl)


def test_does_not_clone_remote_nor_reset_source_in_standby(monitor_only_cluster):
    mgr = monitor_only_cluster
    mgr.remote = make_mysql("remote", "source")
    mgr.cluster_data_handler.get_cluster_state.side_effect = [
        MysqlClusterState.STANDBY.value,
        MysqlClusterState.CREATED.value,
        MysqlClusterState.CREATED.value,
    ]
    mgr.src.get_replica_status.return_value = None
    mgr._load_cluster_data = MagicMock()
    mgr.reconcile_cluster = MagicMock(side_effect=StopRun)
    before = skipped_actions("join_source_to_remote")

    with pytest.raises(StopRun):
        mgr.run()

    assert_cluster_untouched(mgr, mgr.src, mgr.repl, mgr.remote)
    assert skipped_actions("join_source_to_remote") == before + 1


def test_fails_over_when_not_monitor_only(monitor_only_cluster):
    mgr = monitor_only_cluster
    mgr.monitor_only = False
    old_repl = mgr.repl
    mgr.src.ping.side_effect = Exception("connection refused")
    old_repl.get_replica_status.return_value = {"Source_Host": "s1"}
    old_repl.find_replication_problems.return_value = []

    for _ in range(mgr.master_failure_threshold + 1):
        mgr.reconcile_cluster()

    old_repl.reset_replication.assert_called_once()
    assert mgr.cluster_data_handler.set_mysql_role.call_count == 2
