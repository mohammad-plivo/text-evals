#!/bin/zsh
# Dump the DB truth of a dev flow into a build_flow.py dump dir: <uuid>.json per node (Redis :CONFIG), names.txt
# (uuid|name|component) and connections.json (latest phlo_connections row). Needs a valid dev AWS session.
#   dump_dev_flow.sh <flow-uuid> <out-dir>      # opens the SSM tunnels itself (redis 6380, phlo ro 5434) and closes them
set -u
FLOW="$1"; OUT="$2"; mkdir -p "$OUT"
TUN=~/.claude/skills/cx-db-tunnel/scripts/tunnel.sh
bash "$TUN" redis > "$OUT/tunnel-redis.log" 2>&1 & R=$!
bash "$TUN" phlo ro 5434 > "$OUT/tunnel-phlo.log" 2>&1 & P=$!
trap 'kill $R $P 2>/dev/null' EXIT
for i in $(seq 1 30); do redis-cli -h localhost -p 6380 -t 2 ping 2>/dev/null | grep -q PONG && break; sleep 2; done
redis-cli -h localhost -p 6380 ping | grep -q PONG || { echo "redis tunnel not up"; exit 2; }
n=0
for key in $(redis-cli -h localhost -p 6380 --scan --pattern "PHLO:${FLOW}:NODE:*:CONFIG"); do
  uuid=${${key#PHLO:${FLOW}:NODE:}%:CONFIG}
  redis-cli -h localhost -p 6380 --raw GET "$key" > "$OUT/$uuid.json"; n=$((n+1))
done
echo "node configs: $n"
for i in $(seq 1 30); do PGCONNECT_TIMEOUT=3 psql -h localhost -p 5434 -U "${PHLO_DB_USER:-contacto_user}" -d "${PHLO_DB_NAME:-contacto}" -Atc "select 1" >/dev/null 2>&1 && break; sleep 2; done
PSQL="psql -h localhost -p 5434 -U ${PHLO_DB_USER:-contacto_user} -d ${PHLO_DB_NAME:-contacto} -At"
$PSQL -c "\dt" | grep -i "phlo" > "$OUT/tables.txt"; echo "phlo tables: $(wc -l < "$OUT/tables.txt")"
$PSQL -c "SELECT connections::text FROM phlo_connections WHERE flow_id=(SELECT id FROM phlo WHERE uuid='${FLOW}') AND NOT is_deleted ORDER BY version DESC LIMIT 1" > "$OUT/connections.json"
echo "connections bytes: $(wc -c < "$OUT/connections.json")"
# names: try the usual node table shapes; the first query that answers wins
for q in \
  "SELECT n.uuid||'|'||n.name||'|'||n.component_name FROM phlo_nodes n WHERE n.flow_id=(SELECT id FROM phlo WHERE uuid='${FLOW}') AND NOT n.is_deleted" \
  "SELECT n.uuid||'|'||n.name||'|'||c.name FROM phlo_node n JOIN component c ON c.id=n.component_id WHERE n.phlo_id=(SELECT id FROM phlo WHERE uuid='${FLOW}') AND NOT n.is_deleted"; do
  if $PSQL -c "$q" > "$OUT/names.txt" 2>"$OUT/names.err" && [ -s "$OUT/names.txt" ]; then echo "names rows: $(wc -l < "$OUT/names.txt")"; break; fi
done
[ -s "$OUT/names.txt" ] || { echo "names query failed; inspect $OUT/tables.txt and write the query by hand"; cat "$OUT/names.err" | tail -2; }
