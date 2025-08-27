#!/usr/bin/env bash
set -e

# namespaces
kubectl create ns monitoring --dry-run=client -o yaml | kubectl apply -f -

# helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana             https://grafana.github.io/helm-charts
helm repo update

# kube-prometheus-stack
helm upgrade --install kube-prom prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.service.type=NodePort \
  --set grafana.service.nodePort=30080 \
  --set prometheus.service.type=NodePort \
  --set prometheus.service.nodePort=30900
