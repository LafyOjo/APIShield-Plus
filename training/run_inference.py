"""Simple live traffic inference example.

This script watches network packets in real-time, extracts a handful
of basic features, and feeds them into a pre-trained Keras model.
It also exposes CPU/memory usage as Prometheus metrics for monitoring.
"""

import argparse
import time
from typing import List

import psutil
from prometheus_client import Gauge, start_http_server

import numpy as np
from scapy.all import sniff, TCP
from tensorflow import keras

# Prometheus metrics — these let external dashboards
# track CPU usage and memory consumption of this process.
CPU_PERCENT = Gauge("ml_cpu_percent", "CPU usage percentage")
MEM_BYTES = Gauge("ml_memory_bytes", "Memory usage in bytes")


def extract_features(pkts: List) -> np.ndarray:
    """
    Take a list of packets and boil them down into a small
    numeric feature vector. This makes the raw network data
    digestible for our ML model.
    """
    total = len(pkts)
    if not total:
        # If no packets were captured in the window,
        # return an all-zero vector to keep dimensions consistent.
        return np.zeros((1, 8), dtype=np.float32)

    # Calculate lengths of each packet so we can compute stats later.
    lengths = [len(p) for p in pkts]

    # Count SYN and ACK flags to get a feel for connection activity.
    syn_count = sum(1 for p in pkts if p.haslayer(TCP) and p[TCP].flags == 'S')
    ack_count = sum(1 for p in pkts if p.haslayer(TCP) and p[TCP].flags == 'A')

    # Build our feature vector: total packets, size stats,
    # proportion of SYN/ACK, and overall traffic volume in KB.
    features = np.array([
        total,
        np.mean(lengths),
        np.std(lengths),
        syn_count / total,
        ack_count / total,
        max(lengths),
        min(lengths),
        sum(lengths) / 1024,  # total traffic in KB
    ], dtype=np.float32)

    # Reshape into a 2D array because Keras expects [batch, features].
    return features.reshape(1, -1)


def main(iface: str, model_path: str, duration: float):
    """
    Main event loop. Loads the ML model, then repeatedly
    captures packets, extracts features, and makes predictions.
    """
    # Start up a Prometheus HTTP server so resource metrics
    # can be scraped externally (e.g. at http://localhost:8002).
    start_http_server(8002)

    # Load the trained Keras model from disk.
    model = keras.models.load_model(model_path)
    print(f"Loaded model from {model_path}")

    # Endless loop: keep capturing and scoring network traffic.
    while True:
        print(f"Capturing {duration}s of traffic on {iface}...")

        # Sniff packets for the given time window.
        pkts = sniff(iface=iface, timeout=duration)

        # Turn raw packets into a numerical feature vector.
        feats = extract_features(pkts)

        # Ask the ML model for a prediction.
        prob = float(model.predict(feats, verbose=0)[0][0])
        print(f"Prediction for last window: {prob:.4f}")

        # Update Prometheus gauges with current CPU + memory usage.
        CPU_PERCENT.set(psutil.cpu_percent())
        MEM_BYTES.set(psutil.Process().memory_info().rss)

        # Small sleep to avoid hammering the system.
        time.sleep(0.5)


if __name__ == "__main__":
    # Argument parsing so this script can be run from the command line
    # with different interfaces, model files, and capture durations.
    parser = argparse.ArgumentParser(description="Run live ML inference")
    parser.add_argument("--iface", default="eth0", help="Network interface")
    parser.add_argument("--model", default="training/trained_model.h5",
                        help="Path to trained Keras model")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Capture window in seconds")
    args = parser.parse_args()

    # Kick off the main loop with user-provided parameters.
    main(args.iface, args.model, args.duration)
