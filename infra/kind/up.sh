# infra/kind/up.sh
#!/usr/bin/env bash
set -e
bash infra/kind/00-create-cluster.sh
kubectl create ns demo
bash infra/kind/01-prom-grafana.sh
echo "Cluster ready. Start the demo shop locally (see demo-shop/README.md)."
echo "Port-forward Grafana & Prometheus in separate shells."
