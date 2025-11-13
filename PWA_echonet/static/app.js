function updateClock() {
    let now = new Date();
    document.getElementById("clock").innerText =
        now.toLocaleTimeString();
}

async function updateInfo() {
    let r = await fetch("/info");
    let data = await r.json();

    document.getElementById("cpu").innerText = data.cpu;
    document.getElementById("battery").innerText = data.battery;
}

async function updateNodes() {
    let r = await fetch("/nodes");
    let nodes = await r.json();

    let list = document.getElementById("node-list");
    list.innerHTML = "";

    nodes.forEach(n => {
        let item = document.createElement("li");
        item.innerText = `${n.id} — CPU: ${n.cpu}% — Battery: ${n.battery}%`;
        list.appendChild(item);
    });
}

setInterval(() => {
    updateInfo();
    updateNodes();
}, 2000);

updateInfo();
updateNodes();
