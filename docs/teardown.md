# Teardown

The replication instance and the databases bill by the hour, so teardown happened the same day. Nothing has
deletion protection and there's no `Deny` statement anywhere, so every delete works for the account
administrator.

Run from the repo folder after `source ./env.sh`.

## A: the application and DMS

[`29`](screenshots/29-step12-teardown-dms.png)

```bash
python3 scripts/ssm_run.py sh "$SRC_ID" "orders-app stop"
for t in "$TASK_ARN" "$VAL_TASK_ARN" "$VAL2_TASK_ARN" "$PG_TASK_ARN"; do s=$(aws dms describe-replication-tasks --filters Name=replication-task-arn,Values="$t" --query 'ReplicationTasks[0].Status' --output text); if [ "$s" = "running" ]; then aws dms stop-replication-task --replication-task-arn "$t" --query ReplicationTask.Status --output text; aws dms wait replication-task-stopped --filters Name=replication-task-arn,Values="$t"; fi; aws dms delete-replication-task --replication-task-arn "$t" --query ReplicationTask.Status --output text; done
for t in "$TASK_ARN" "$VAL_TASK_ARN" "$VAL2_TASK_ARN" "$PG_TASK_ARN"; do aws dms wait replication-task-deleted --filters Name=replication-task-arn,Values="$t"; done
for ep in "$SRC_EP" "$AURORA_EP" "$PG_EP"; do aws dms delete-endpoint --endpoint-arn "$ep" --query Endpoint.Status --output text; done
aws dms delete-replication-instance --replication-instance-arn "$RI_ARN" --query ReplicationInstance.ReplicationInstanceStatus --output text
aws logs delete-log-group --log-group-name dms-tasks-retail-dms
```

A task can't be deleted while it's running, endpoints can't be deleted while tasks use them, and the instance
can't be deleted while it has tasks: hence the order. The app's last order before it stopped was 204,409, on
Aurora.

## B: databases and the server

[`30`](screenshots/30-step12-teardown-databases-and-server.png)

```bash
aws rds delete-db-instance --db-instance-identifier retail-aurora-writer --query DBInstance.DBInstanceStatus --output text
aws rds delete-db-instance --db-instance-identifier retail-pg --skip-final-snapshot --delete-automated-backups --query DBInstance.DBInstanceStatus --output text
aws ec2 terminate-instances --instance-ids "$SRC_ID" --query 'TerminatingInstances[].CurrentState.Name' --output text
aws rds wait db-instance-deleted --db-instance-identifier retail-aurora-writer
aws rds delete-db-cluster --db-cluster-identifier retail-aurora --skip-final-snapshot --query DBCluster.Status --output text
aws dms wait replication-instance-deleted --filters Name=replication-instance-arn,Values="$RI_ARN"
aws dms delete-replication-subnet-group --replication-subnet-group-identifier retail-dms-subnets
```

An Aurora cluster can only be deleted once its instances are gone, hence the wait. `delete-db-cluster` printed
`available`: the status at the moment the request was accepted, before deletion starts.

## C: secret, IAM, network

```bash
aws rds wait db-instance-deleted --db-instance-identifier retail-pg
until [ -z "$(aws rds describe-db-clusters --query 'DBClusters[?DBClusterIdentifier==`retail-aurora`].Status' --output text)" ]; do sleep 20; done
aws rds delete-db-subnet-group --db-subnet-group-name retail-db-subnets
aws secretsmanager delete-secret --secret-id "$SECRET_ID" --force-delete-without-recovery --query Name --output text
aws iam remove-role-from-instance-profile --instance-profile-name retail-onprem-profile --role-name retail-onprem-role
aws iam delete-instance-profile --instance-profile-name retail-onprem-profile
aws iam delete-role-policy --role-name retail-onprem-role --policy-name read-migration-secret
aws iam detach-role-policy --role-name retail-onprem-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role --role-name retail-onprem-role
if [ "${CREATED_dms_vpc_role:-}" = yes ]; then aws iam detach-role-policy --role-name dms-vpc-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonDMSVPCManagementRole && aws iam delete-role --role-name dms-vpc-role; fi
if [ "${CREATED_dms_cloudwatch_logs_role:-}" = yes ]; then aws iam detach-role-policy --role-name dms-cloudwatch-logs-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonDMSCloudWatchLogsRole && aws iam delete-role --role-name dms-cloudwatch-logs-role; fi
aws ec2 wait instance-terminated --instance-ids "$SRC_ID"
for g in "$AURORA_SG" "$PG_SG" "$SRC_SG" "$DMS_SG"; do aws ec2 delete-security-group --group-id "$g" --query Return --output text; done
for s in "$SUB_DC" "$SUB_DATA_A" "$SUB_DATA_B"; do aws ec2 delete-subnet --subnet-id "$s"; done
aws ec2 delete-route-table --route-table-id "$RT_DC"
aws ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID" && aws ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID"
aws ec2 delete-vpc --vpc-id "$VPC_ID"
```

- The two DMS service roles are deleted only if this build created them (`CREATED_...=yes`). In an account that
  already uses DMS they belong to everyone, and deleting them would break other migrations.
- Security groups go Aurora and PostgreSQL first (they refer to the others), then the on-prem group (refers to
  DMS), then DMS.
- A `DependencyViolation` means a network interface is still being released: wait a minute and run that line again.

I didn't screenshot block C. The clean check below covers its results.

## Clean check

[`31`](screenshots/31-step12-clean-check.png): every line printed nothing.

```bash
aws dms describe-replication-tasks --query 'ReplicationTasks[].ReplicationTaskIdentifier' --output text
aws dms describe-endpoints --query 'Endpoints[].EndpointIdentifier' --output text
aws dms describe-replication-instances --query 'ReplicationInstances[].ReplicationInstanceIdentifier' --output text
aws rds describe-db-clusters --query 'DBClusters[?starts_with(DBClusterIdentifier, `retail-`)].DBClusterIdentifier' --output text
aws rds describe-db-instances --query 'DBInstances[?starts_with(DBInstanceIdentifier, `retail-`)].DBInstanceIdentifier' --output text
aws rds describe-db-cluster-snapshots --snapshot-type manual --query 'DBClusterSnapshots[?starts_with(DBClusterIdentifier, `retail-`)].DBClusterSnapshotIdentifier' --output text
aws ec2 describe-instances --filters Name=tag:Name,Values=retail-db-onprem Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId' --output text
aws ec2 describe-vpcs --filters Name=tag:Name,Values=retail-mig-vpc --query 'Vpcs[].VpcId' --output text
aws secretsmanager list-secrets --query 'SecretList[?starts_with(Name, `retail-migration`)].Name' --output text
aws iam list-roles --query 'Roles[?starts_with(RoleName, `retail-`)].RoleName' --output text
aws logs describe-log-groups --log-group-name-prefix dms-tasks-retail --query 'logGroups[].logGroupName' --output text
aws rds describe-db-subnet-groups --query 'DBSubnetGroups[?DBSubnetGroupName==`retail-db-subnets`].DBSubnetGroupName' --output text
aws dms describe-replication-subnet-groups --query 'ReplicationSubnetGroups[?ReplicationSubnetGroupIdentifier==`retail-dms-subnets`].ReplicationSubnetGroupIdentifier' --output text
```

The VPC can only be deleted once its subnets, security groups and route table are gone, so an empty VPC line
covers those too. The check doesn't list the internet gateway, the instance profile or the two DMS service roles
separately; block C deletes them.
