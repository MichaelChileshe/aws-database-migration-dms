#!/bin/bash
# Boot script for retail-db-onprem: Ubuntu Retail's "on-premises" database server.
# Installs Docker (MySQL 8.0 runs in a container), the PostgreSQL client, and two tools:
#   retail-db   - start MySQL, run SQL on the source / Aurora / PostgreSQL, create users, count rows
#   orders-app  - the order-taking application: writes about three orders a second to whichever database it is pointed at
# Passwords are read from Secrets Manager when needed; these tools never write them to files. (MySQL's root password is
# passed to the container as an environment variable, which Docker keeps in the container's settings on this server.)
set -euxo pipefail
dnf install -y docker postgresql16
systemctl enable --now docker
mkdir -p /data/mysql
touch /etc/retail-db.conf /var/log/orders-app.log

cat > /usr/local/bin/retail-db <<'TOOL'
#!/bin/bash
set -euo pipefail
export AWS_DEFAULT_REGION=@@REGION@@
SECRET_ID="@@SECRET_ID@@"
CONF=/etc/retail-db.conf
AURORA_HOST=""; PG_HOST=""
. "$CONF"

pw() {  # pw <key>: one password from the migration secret (printed only into a pipe or variable)
  aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString --output text \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])"
}
my() {  # my <host> <user> <password-key> [mysql args]: the MySQL 8.0 client inside the container
  local host=$1 user=$2 key=$3; shift 3
  docker exec -i -e MYSQL_PWD="$(pw "$key")" ordersdb mysql -h "$host" -u "$user" "$@"
}
need() { [ -n "$2" ] || { echo "ERROR: $1 is not set yet (retail-db set $1 <endpoint>)"; exit 1; }; }

case "${1:-}" in
  mysql-start)   # mysql-start nobinlog|binlog : (re)start the source database, keeping its data
    mode=${2:?nobinlog or binlog}
    docker stop -t 60 ordersdb >/dev/null 2>&1 || true   # clean shutdown, so restarts need no crash recovery
    docker rm ordersdb >/dev/null 2>&1 || true
    args="--server-id=1"
    if [ "$mode" = binlog ]; then
      args="$args --log-bin=mysql-bin --binlog-format=ROW --binlog-row-image=FULL --binlog-expire-logs-seconds=86400"
    else
      args="$args --skip-log-bin"
    fi
    docker run -d --name ordersdb --restart unless-stopped -p 3306:3306 -v /data/mysql:/var/lib/mysql \
      -e MYSQL_ROOT_PASSWORD="$(pw source_root)" mysql:8.0 $args >/dev/null
    for i in $(seq 1 90); do
      if my 127.0.0.1 root source_root -N -e "SELECT 1" >/dev/null 2>&1; then break; fi
      sleep 2
    done
    my 127.0.0.1 root source_root -t -e "SELECT @@version AS version, @@log_bin AS log_bin, @@binlog_format AS binlog_format, @@binlog_row_image AS row_image, @@binlog_expire_logs_seconds AS binlog_retention_s, @@server_id AS server_id"
    ;;
  users-source)  # the DMS user (replication + read) and the application user
    { echo "CREATE USER IF NOT EXISTS 'dms_user'@'%' IDENTIFIED WITH mysql_native_password BY '$(pw dms_source)';"
      echo "GRANT REPLICATION CLIENT, REPLICATION SLAVE ON *.* TO 'dms_user'@'%';"
      echo "GRANT SELECT ON ubuntu_retail.* TO 'dms_user'@'%';"
      echo "CREATE USER IF NOT EXISTS 'orders_app'@'%' IDENTIFIED WITH mysql_native_password BY '$(pw app)';"
      echo "GRANT SELECT, INSERT, UPDATE ON ubuntu_retail.* TO 'orders_app'@'%';"
      echo "SELECT user, host, plugin FROM mysql.user WHERE user IN ('dms_user','orders_app');"
      echo "SHOW GRANTS FOR 'dms_user'@'%';"; } | my 127.0.0.1 root source_root -t
    ;;
  users-aurora)  # DMS moves data, not users: create the application user on Aurora before cutover
    need aurora "$AURORA_HOST"
    { echo "CREATE USER IF NOT EXISTS 'orders_app'@'%' IDENTIFIED WITH mysql_native_password BY '$(pw app)';"
      echo "GRANT SELECT, INSERT, UPDATE ON ubuntu_retail.* TO 'orders_app'@'%';"
      echo "SELECT user, host, plugin FROM mysql.user WHERE user = 'orders_app';"; } | my "$AURORA_HOST" admin aurora_admin -t
    ;;
  sql)           # sql source|aurora : run SQL from stdin
    case "${2:-}" in
      source) my 127.0.0.1 root source_root -t ;;
      aurora) need aurora "$AURORA_HOST"; my "$AURORA_HOST" admin aurora_admin -t ;;
      *) echo "usage: retail-db sql source|aurora < file.sql"; exit 1 ;;
    esac
    ;;
  psql)          # psql : run SQL from stdin on the PostgreSQL target
    need pg "$PG_HOST"
    PGPASSWORD="$(pw pg_admin)" psql "host=$PG_HOST port=5432 dbname=retail user=pgadmin sslmode=require" -f -
    ;;
  counts)        # counts source|aurora : row counts per table + the newest order id, on one line
    q="SELECT (SELECT COUNT(*) FROM ubuntu_retail.customers), (SELECT COUNT(*) FROM ubuntu_retail.products), (SELECT COUNT(*) FROM ubuntu_retail.orders), (SELECT COUNT(*) FROM ubuntu_retail.order_items), (SELECT MAX(order_id) FROM ubuntu_retail.orders)"
    case "${2:-}" in
      source) my 127.0.0.1 root source_root -N -e "$q" ;;
      aurora) need aurora "$AURORA_HOST"; my "$AURORA_HOST" admin aurora_admin -N -e "$q" ;;
      *) echo "usage: retail-db counts source|aurora"; exit 1 ;;
    esac
    ;;
  set)           # set aurora|pg <endpoint>
    key=$(echo "${2:?aurora or pg}" | tr a-z A-Z)_HOST
    sed -i "/^$key=/d" "$CONF"; echo "$key=${3:?endpoint}" >> "$CONF"; cat "$CONF"
    ;;
  *) echo "usage: retail-db mysql-start|users-source|users-aurora|sql|psql|counts|set"; exit 1 ;;
esac
TOOL

cat > /usr/local/bin/orders-app <<'TOOL'
#!/bin/bash
# orders-app: Ubuntu Retail's order-taking application, reduced to its database writes.
# Each loop: insert an order + one line, set its total, mark a random older order SHIPPED. Every result is logged
# with a UTC timestamp, so the cutover downtime can be read straight from the log.
set -uo pipefail
export AWS_DEFAULT_REGION=@@REGION@@
SECRET_ID="@@SECRET_ID@@"
LOG=/var/log/orders-app.log; PIDF=/run/orders-app.pid; CONF=/etc/retail-db.conf
AURORA_HOST=""; . "$CONF"

case "${1:-}" in
  start)   # start source|aurora
    target=${2:-source}
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "already running (pid $(cat "$PIDF"))"; exit 0; fi
    nohup /usr/local/bin/orders-app run "$target" >/dev/null 2>&1 &
    echo $! > "$PIDF"; sleep 2; echo "orders-app started against $target"; tail -n 2 "$LOG"
    ;;
  run)
    target=$2; host=127.0.0.1
    if [ "$target" = aurora ]; then host=$AURORA_HOST; fi
    PW=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString --output text \
         | python3 -c "import json,sys; print(json.load(sys.stdin)['app'])")
    while true; do
      t=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
      if out=$(docker exec -e MYSQL_PWD="$PW" ordersdb mysql -h "$host" -u orders_app -N ubuntu_retail -e "
          INSERT INTO orders (customer_id, status, total_zar) VALUES (1 + FLOOR(RAND() * 5000), 'NEW', 0);
          SET @o = LAST_INSERT_ID();
          INSERT INTO order_items (order_id, product_id, qty, price_zar) VALUES (@o, 1 + FLOOR(RAND() * 500), 1 + FLOOR(RAND() * 3), 149.99);
          UPDATE orders SET total_zar = (SELECT SUM(qty * price_zar) FROM order_items WHERE order_id = @o) WHERE order_id = @o;
          SET @r = 1 + FLOOR(RAND() * 200000);
          UPDATE orders SET status = 'SHIPPED' WHERE order_id = @r;
          SELECT @o;" 2>&1); then
        echo "$t OK $target order=$out" >> "$LOG"
      else
        echo "$t FAIL $target $(echo "$out" | tail -n 1)" >> "$LOG"
      fi
      sleep 0.2
    done
    ;;
  stop)
    if [ -f "$PIDF" ]; then kill "$(cat "$PIDF")" 2>/dev/null || true; rm -f "$PIDF"; fi
    sleep 1; echo "orders-app stopped"; tail -n 1 "$LOG"
    ;;
  status)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "running (pid $(cat "$PIDF"))"; else echo "stopped"; fi
    echo "OK writes logged: $(grep -c ' OK ' "$LOG")   FAIL: $(grep -c ' FAIL ' "$LOG")"; tail -n 3 "$LOG"
    ;;
  log)     # log [n]
    tail -n "${2:-20}" "$LOG"
    ;;
  *) echo "usage: orders-app start source|aurora | stop | status | log [n]"; exit 1 ;;
esac
TOOL

chmod 755 /usr/local/bin/retail-db /usr/local/bin/orders-app
echo "retail-db-onprem ready"
