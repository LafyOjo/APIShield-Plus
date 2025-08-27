# infra/kind/down.sh
#!/usr/bin/env bash
set -e
kind delete cluster --name cred-demo
echo "Cluster deleted."
