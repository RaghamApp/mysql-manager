## deploy with docker
You can use [docker-compose.yaml](./../docker-compose.yaml) to deploy all needed 
services. Make sure to uncomment volumes if you need persistence.
```sh 
docker compose up etcd -d 
```
It deploys etcd to store state of the cluster. 
After running the etcd, we need to do some inital setup in it.
First create root user and another user with limited privileges for MySQL Manager. 
```sh
docker compose exec etcd etcdctl user add root --new-user-password="password"
docker compose exec etcd etcdctl user grant-role root root
docker compose exec etcd etcdctl user add mm --new-user-password="password"
docker compose exec etcd etcdctl role add mm 
docker compose exec etcd etcdctl role grant-permission mm --prefix=true readwrite mm/cluster1/
docker compose exec etcd etcdctl user grant-role mm mm
docker compose exec etcd etcdctl auth enable
```      
We created `mm` user with password `password`. In a production environment you need to set a 
much stronger password. User `mm` is granted access to `mm/cluster1/` prefix in etcd. Note that 
the environment variables in `mm` container must match the values given above. 

Then run all other containers:
```sh
docker compose up -d --build
```
It deploys two MySQL servers, their exporters and a ProxySQL. MySQL Manager is set up by building 
an image from Dockerfile at the root of the project. Now start cluster with this command:
```sh
docker compose exec mm python cli/mysql-cli.py init -f /etc/mm/cluster-spec.yaml
```
Running `python cli/mysql-cli.py init -f /etc/mm/cluster-spec.yaml` in `mm` makes MySQL Manager 
to start cluster setup, watch for their state and failover if needed. After a minute check `mm`
logs:
```sh
docker compose logs mm -f 
```
You should see these lines in its logs:
```log
Source is mysql-s1
Replica is mysql-s2
```
You can check server states by running this:
```sh
docker compose exec mm python cli/mysql-cli.py mysql get-cluster-status
```
The output is like this:
```log
source=up
replica=up
```


## monitor-only mode
To run MySQL Manager only as a health checker, start it with the `--monitor-only` flag or set
the `MM_MONITOR_ONLY=true` environment variable:
```sh
python cli/mysql-cli.py mysql run --monitor-only
## or
MM_MONITOR_ONLY=true python cli/mysql-cli.py mysql run
```
In this mode MySQL Manager keeps checking the cluster and reports problems in its logs and metrics,
but it never changes the MySQL servers or the cluster data in etcd: it does not clone, fail over,
restart or reset replication, nor run the initial setup. Every action it would have taken is logged
with a `[monitor-only] Skipping <action>: <reason>` line and counted in the
`mysql_manager_skipped_actions_total{action="<action>"}` metric.

Metrics (served on port 8000):
- `mysql_manager_monitor_only_mode`: 1 when running in monitor-only mode
- `mysql_master_up`, `mysql_replica_up`: whether the source and replica are up
- `mysql_master_health_check_failures`: consecutive failed health checks of the source
- `mysql_replication_problem{host, problem}`: replication problems currently detected on the replica
- `mysql_manager_skipped_actions_total{action}`: actions skipped because of monitor-only mode


## destroy
to destroy the containers run:
```sh
docker compose down
```
