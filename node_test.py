import time
import json
import socket
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser

# ----------------------------
# CONFIG — change this per laptop
# ----------------------------
NODE_ID = "nodeA"   # change to "nodeB" on the second laptop
PORT = 9999
SKILLS = ["test-skill"]  # irrelevant, just for demo
# ----------------------------


def get_local_ip():
    """Get LAN IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class DiscoveryListener:
    """Listens for other nodes broadcasting on the LAN."""
    def add_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return

        node_ip = socket.inet_ntoa(info.addresses[0])
        node_id = info.properties[b"id"].decode()
        skills = json.loads(info.properties[b"skills"].decode())

        print(f"✨ FOUND NODE → {node_id} @ {node_ip}:{info.port}, skills={skills}")

    def remove_service(self, zeroconf, service_type, name):
        print(f"💦 Node disappeared: {name}")


def start_advertising():
    """Advertise this node over mDNS."""
    zc = Zeroconf()
    ip = get_local_ip()

    props = {
        "id": NODE_ID,
        "skills": json.dumps(SKILLS)
    }

    info = ServiceInfo(
        "_echotest._tcp.local.",
        f"{NODE_ID}._echotest._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=PORT,
        properties=props,
        server=f"{NODE_ID}.local.",
    )

    zc.register_service(info)
    print(f"🐣 ADVERTISING: {NODE_ID} @ {ip}:{PORT}")

    return zc, info


def start_discovery(zc):
    """Start browsing for other nodes."""
    print("🔎 STARTING DISCOVERY...")
    return ServiceBrowser(zc, "_echotest._tcp.local.", DiscoveryListener())


if __name__ == "__main__":
    zc, info = start_advertising()
    browser = start_discovery(zc)

    print("\n🔥 Test started. If another laptop is running, you should see it appear.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Stopping...")
        zc.unregister_service(info)
        zc.close()
