# Mininet Traffic Generation

This example script creates a tiny Mininet topology on the local machine. It starts two hosts connected to a single switch, then generates a burst of HTTP traffic. A small Python HTTP server runs on `h2` while `h1` issues requests.

The demo shop referenced in the root README lives in the `../demo-shop` directory.

Run the script with root privileges so Mininet can configure network namespaces:

```bash
sudo python3 gen_traffic.py
```

After sending a few baseline requests and a larger "attack" burst, the script drops to the Mininet CLI. Use commands like `pingall` or `iperf` to interact with the virtual network. Type `exit` to stop the network.

This provides a lightweight way to produce repeatable traffic patterns when testing the detector on a Raspberry Pi or other host.
