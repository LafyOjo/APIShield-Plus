# Raspberry Pi Setup Guide

This document describes how to run the APIShield+ demo on a Raspberry Pi 4. These instructions cover the edge-hosted monitoring web service only (backend and frontend). The other optional Pi integrations mentioned in the main README are beyond the scope of this file.

## Educational use only

This project is intended for testing security concepts in controlled environments for educational purposes. Attacking systems without explicit authorization is strictly prohibited. The RockYou-derived password list in `scripts/data/rockyou.txt` is provided solely as a demonstration resource.

## Prerequisites

- Raspberry Pi 4 running Raspberry Pi OS (32- or 64-bit)
- Python 3.12 or newer
- Node.js (tested with Node 18)
- Git

The Pi should be connected to your local network so you can access the dashboard from another machine or a small SPI display.

## 1. Clone the repository

```bash
git clone https://github.com/your-username/Kubernetes-Credential-Stuffing-and-API-Poisoning.git
cd Kubernetes-Credential-Stuffing-and-API-Poisoning
```

## 2. Set up the backend

Create a Python virtual environment and install the backend requirements:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with at least `SECRET_KEY` defined (see the main README for all options). Run the Alembic migration then start the API server:

```bash
alembic upgrade head
set -a
source .env
set +a
python server.py  # binds 0.0.0.0:8001 so other devices can connect
```

The backend will expose metrics and API routes on port `8001`.

## 3. Set up the frontend

Open a new terminal on the Pi, then install the frontend dependencies and start the React development server:

# Download and run the NodeSource setup script for Node.js v20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -

# Install Node.js (which includes npm)
sudo apt-get install -y nodejs

```bash
cd frontend
npm install
HOST=0.0.0.0 REACT_APP_API_BASE=http://<pi-ip>:8001 npm start
```

The dashboard will be available at [http://<pi-ip>:3000](http://<pi-ip>:3000). Replace `<pi-ip>` with the Pi's address on your LAN. If the backend runs on another host, adjust the `REACT_APP_API_BASE` variable accordingly.

Which can be done by typing in on the terminal `hostname -I`

## 4. Launch both services together (optional)


Once both the backend and frontend dependencies are installed you can start them
together from the repository root using the helper script:

```bash
python rpi/start_edge_service.py
```

The script loads environment variables from `backend/.env`, launches the API on
`0.0.0.0:8001`, then spawns the React development server bound to `0.0.0.0`. The
dashboard will be reachable at `http://<pi-ip>:3000`. Press `Ctrl+C` to stop
both processes.

## 5. Optional: attach a 3.5" SPI display

Once both the backend and frontend dependencies are installed you can start them
together from the repository root using the helper script:

```bash
python rpi/start_edge_service.py
```

The script loads environment variables from `backend/.env`, launches the API on
`0.0.0.0:8001`, then spawns the React development server bound to `0.0.0.0`. The
dashboard will be reachable at `http://<pi-ip>:3000`. Press `Ctrl+C` to stop
both processes.

## 5. Optional: attach a 3.5" SPI display

If you connect a 3.5" SPI display to the Pi's GPIO header, configure the appropriate framebuffer driver for your model. Once the display shows the Pi's desktop you can open a browser at `http://localhost:3000` **or** run the lightweight Python dashboard:

```bash
pip install -r rpi/requirements.txt
python rpi/spi_display.py --api-base http://localhost:8001
```

The script polls `/api/alerts/stats` and renders the latest counts using `pygame`.

## 6. Next steps

With the web service running locally, you can explore the more advanced Raspberry Pi integrations outlined in the main README, such as local traffic generation with Mininet or on-device machine learning inference.


### Run live ML inference

Once you have a trained model copied to `training/trained_model.h5` you can capture traffic and evaluate it with:

```bash
python training/run_inference.py --iface eth0
```

### Run the SDN controller

Install Open vSwitch and the Python dependencies:

```bash
sudo apt install openvswitch-switch
pip install -r sdn-controller/requirements.txt
```

Start the controller and point the OVS bridge at it:

```bash
ryu-manager sdn-controller/simple_monitor.py &
sudo ovs-vsctl set-controller br0 tcp:127.0.0.1:6633
```

Flow statistics will be printed every few seconds. Customize the script to
forward these stats to your running detector API.

### Touchscreen feature menu

If you have the Pi connected to a small touchscreen you can launch all of the
features from a single menu:

```bash
python rpi/menu.py
```

Tap a button or press the corresponding number key to start a feature. Press
`Esc` to stop the running process and return to the menu.
