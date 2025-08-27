from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
import time


def run():
    """Spin up a simple topology and generate HTTP traffic."""
    setLogLevel('info')

    net = Mininet(link=TCLink, switch=OVSSwitch)
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    s1 = net.addSwitch('s1')
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.start()

    # Start a basic HTTP server on h2
    h2.cmd('python3 -m http.server 8080 &')

    # Give the server time to start
    time.sleep(1)

    print("Sending baseline traffic")
    for _ in range(5):
        h1.cmd('curl -s http://10.0.0.2:8080 > /dev/null')

    print("Sending attack traffic")
    for _ in range(50):
        h1.cmd('curl -s http://10.0.0.2:8080 > /dev/null')

    CLI(net)
    net.stop()


if __name__ == "__main__":
    run()
