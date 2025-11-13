from flask import Flask, send_from_directory, jsonify
import subprocess, json

app = Flask(__name__, static_url_path='', static_folder='static')

def get_battery():
    try:
        out = subprocess.check_output(["termux-battery-status"])
        data = json.loads(out.decode())
        return data.get("percentage")
    except:
        return None

def get_cpu():
    try:
        out = subprocess.check_output(["dumpsys", "cpuinfo"])
        txt = out.decode()
        # Find first number in the output
        num = "".join(c for c in txt if c.isdigit())
        return float(num) if num else 0.0
    except:
        return 0.0

@app.route("/info")
def info():
    return {
        "cpu": get_cpu(),
        "battery": get_battery(),
        "status": "online",
    }

@app.route("/nodes")
def nodes():
    return jsonify([])

@app.route("/service-worker.js")
def sw():
    return send_from_directory(".", "service-worker.js")

@app.route("/")
def root():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
