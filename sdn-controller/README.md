# Lightweight SDN Controller

This directory contains a minimal [Ryu](https://osrg.github.io/ryu/) controller example. It can be run on a Raspberry Pi alongside Open vSwitch to collect basic flow statistics and optionally send them to the detector API.

The demo shop used for demonstrations resides in `../demo-shop`.

## Installation

```
pip install -r sdn-controller/requirements.txt
```

You will also need Open vSwitch installed on the host so that the switch can connect to the controller. On Raspberry Pi OS:

```
sudo apt install openvswitch-switch
```

## Running the controller

1. Start Open vSwitch and create a bridge connected to your network interfaces. Example:

```
sudo systemctl start openvswitch-switch
sudo ovs-vsctl add-br br0
sudo ovs-vsctl add-port br0 eth0
sudo ovs-vsctl add-port br0 eth1
```

2. Launch the Ryu app which prints flow statistics every few seconds:

```
ryu-manager sdn-controller/simple_monitor.py
```

By default the controller listens on TCP port 6633. Point your switch at the controller IP address, e.g.:

```
sudo ovs-vsctl set-controller br0 tcp:127.0.0.1:6633
```

The script will periodically request flow statistics from the switch and log them. Edit `simple_monitor.py` if you want to forward these stats to the ML classifier running on the same Pi.
