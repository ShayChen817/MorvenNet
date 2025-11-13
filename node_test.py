import time
import json
import socket
import psutil
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser

# ----------------------------
# CHANGE THIS PER DEVICE
# ----------------------------
NODE_ID = "nodeA"       # <---- change to “nodeB” on the second laptop
PORT = 9999
SKILLS = ["test-skill"]

# Maximum "weight" this device can handle (your decision)
MAX_LOAD = 10
current_load = 0
# ----------------------------


def get_local_ip():
    """Get LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_battery():
    """Get battery percentage or None if unavailable."""
    try:
        bat = psutil.sensors_battery()
        if bat:
            return bat.percent
        return None
    except:
        return None


def compute_health(cpu, battery, load):
    """Define a health score (0-1)"""
    score = 1.0

    # CPU penalty
    if cpu > 80:
        score -= 0.3
    elif cpu > 50:
        score -= 0.15

    # Battery penalty
    if battery is not None:
        if battery < 20:
            score -= 0.4
        elif battery < 50:
            score -= 0.2

    # Load penalty
    if load > MAX_LOAD * 0.75:
        score -= 0.2
    elif load > MAX_LOAD * 0.5:
        score -= 0.1

    return max(score, 0.0)


def get_node_metrics():
    cpu = psutil.cpu_percent()
    battery = get_battery()

    health = compute_health(cpu, battery, current_load)

    return {
        "cpu": cpu,
        "battery": battery,
        "load": current_load,
        "max_load": MAX_LOAD,
        "health": health,
    }


class DiscoveryListener:

    def add_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return

        node_ip = socket.inet_ntoa(info.addresses[0])
        node_id = info.properties[b"id"].decode()

        if node_id == NODE_ID:
            return

        device_metrics = json.loads(info.properties[b"metrics"].decode())
        skills = json.loads(info.properties[b"skills"].decode())

        print(f"\n✨ FOUND NODE → {node_id} @ {node_ip}:{info.port}")
        print(f"   skills:    {skills}")
        print(f"   cpu:       {device_metrics['cpu']}%")
        print(f"   battery:   {device_metrics['battery']}")
        print(f"   load:      {device_metrics['load']} / {device_metrics['max_load']}")
        print(f"   health:    {device_metrics['health']:.2f}")

    def update_service(self, zc, service_type, name):
        # not needed now
        pass

    def remove_service(self, zc, service_type, name):
        print(f"💦 Node disappeared: {name}")


def advertise():
    """Advertise node metrics via Zeroconf."""
    zc = Zeroconf()
    ip = get_local_ip()

    while True:
        # Create metrics object
        metrics = get_node_metrics()
        props = {
            "id": NODE_ID,
            "skills": json.dumps(SKILLS),
            "metrics": json.dumps(metrics)
        }

        info = ServiceInfo(
            "_echotest._tcp.local.",
            f"{NODE_ID}._echotest._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=PORT,
            properties=props,
        )

        # Register (or update) the service every 3 seconds
        zc.register_service(info)
        time.sleep(3)
        zc.unregister_service(info)


if __name__ == "__main__":
    # Start advertiser in background thread
    import threading
    adv_thread = threading.Thread(target=advertise, daemon=True)
    adv_thread.start()

    # Start discovery browser
    zc = Zeroconf()
    ServiceBrowser(zc, "_echotest._tcp.local.", DiscoveryListener())

    print("\n🔥 Running — waiting for other devices with metrics...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Stopping...")
        zc.close()
