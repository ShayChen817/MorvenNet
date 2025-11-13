from flask import Flask, send_from_directory, jsonify
import subprocess, json

app = Flask(__name__, static_url_path='', static_folder='static')

# ----------- DEVICE METRICS ----------
def get_battery():
    try:
        out = subprocess.check_output(["termux-battery-status"])
        return json.loads(out.decode())["percentage"]
    except:
        return None

def get_cpu():
    try:
        out = subprocess.check_output("top -bn1 | head -n 5", shell=True)
        txt = out.decode().lower()
        for line in txt.splitlines():
            if "cpu" in line and "%" in line:
                nums = "".join(c for c in line if c.isdigit())
                return float(nums) if nums else 0.0
        return 0.0
    except:
        return 0.0

@app.route("/info")
def info():
    return {
        "cpu": get_cpu(),
        "battery": get_battery(),
        "status": "online",
    }

# (Optional) For discovery: put your Zeroconf node list here
@app.route("/nodes")
def nodes():
    # For demo, a fake device list:
    return jsonify([
        {"id": "phoneNode", "ip": "127.0.0.1", "cpu": get_cpu(), "battery": get_battery()},
    ])

# ----------- PWA FILES ----------
@app.route("/service-worker.js")
def sw():
    return send_from_directory(".", "service-worker.js")

@app.route("/")
def root():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
