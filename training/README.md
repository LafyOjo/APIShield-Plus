# On-Device ML Inference

This directory contains a small example for running the trained TensorFlow model directly on a Raspberry Pi (or any host). The `run_inference.py` script captures live packets with **Scapy**, extracts a handful of features, then feeds them into `trained_model.h5`.

For end-to-end testing with the Sock Shop application located at `../sockshop-master`, see the main README.

```
pip install -r training/requirements.txt
python training/run_inference.py --iface eth0 --model training/trained_model.h5
```

The script loads packets for 10 seconds at a time, computes simple statistics (total packets, average length, TCP SYN ratio, etc.), and prints the predicted probability of an attack for each window.

Place your trained model file at `training/trained_model.h5` before running.
