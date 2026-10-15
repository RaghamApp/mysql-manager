from prometheus_client import Counter, Gauge 

# Prometheus Metrics
# Counters
FAILOVER_ATTEMPTS = Counter('mysql_failover_attempts', 'Number of failover attempts made')
REPLICATION_RESTARTS = Counter('mysql_replication_restarts', 'Number of replication restarts on replicas')
CLUSTER_FAILURES = Counter('mysql_cluster_failures', 'Total number of cluster failures (master and replica down)')
SKIPPED_ACTIONS = Counter(
    'mysql_manager_skipped_actions',
    'Number of actions that would have been run on the cluster but were skipped because of monitor-only mode',
    ["action"],
)

# Gauges
mysql_status_labels = ["host"]
MASTER_UP_STATUS = Gauge(
    'mysql_master_up', 
    'Current status of the MySQL master (1=up, 0=down)',
    mysql_status_labels,
)
REPLICA_UP_STATUS = Gauge(
    'mysql_replica_up',
    'Current status of the MySQL replica (1=up, 0=down)',
    mysql_status_labels,
)
REPLICATION_PROBLEM = Gauge(
    'mysql_replication_problem',
    'Replication problems currently detected on the replica (1=detected)',
    ["host", "problem"],
)
MASTER_HEALTH_CHECK_FAILURES = Gauge(
    'mysql_master_health_check_failures',
    'Number of consecutive failed health checks of the MySQL master',
    mysql_status_labels,
)
MONITOR_ONLY_MODE = Gauge(
    'mysql_manager_monitor_only_mode',
    'Whether mysql manager runs in monitor-only mode and does not change the cluster (1=monitor-only)',
)
