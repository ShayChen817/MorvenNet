# echonet_node.py
import json
import re
import requests
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import os
from dotenv import load_dotenv

# 从项目根目录的 .env 加载环境变量（不会把密钥写入源码）
load_dotenv()

# 把 frontend 目录作为静态资源目录（避免跨域，便于直接在同一服务下提供 UI）
app = Flask(__name__, static_folder='frontend', static_url_path='')


# 根路径返回前端页面 index.html，避免浏览器访问 / 时 404
@app.route('/', methods=['GET'])
def root_index():
    # Use an absolute path to be robust against different working directories
    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
    return send_from_directory(frontend_dir, 'index.html')

# ====== 读取配置 ======
with open("nodes.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SELF_ID = CONFIG["self_id"]
SELF_URL = CONFIG["self_url"]
NODES = CONFIG["nodes"]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment/.env")

# 新版 OpenAI Python 客户端
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- Minimal user store (token -> user id)
USERS = {}
if os.path.exists('users.json'):
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            for u in data.get('users', []):
                USERS[u['token']] = u['id']
    except Exception:
        USERS = {}
else:
    # create a default test user (convenience for local testing)
    USERS['testtoken123'] = 'user1'

# In-memory task store: task_id -> { owner_token, pipeline, final_state, status }
TASK_STORE = {}

import uuid

def _require_token(req):
    token = req.headers.get('X-User-Token') or req.args.get('token')
    if not token:
        return None, ('missing X-User-Token header', 401)
    if token not in USERS:
        return None, ('invalid token', 403)
    return token, None

# ====== 定义本节点的技能实现 ======

def skill_generate_poem_en(state, params):
    prompt = params.get("prompt", "Write a short poem about i love morven.")
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    # new client returns structure similar to legacy; access the content
    poem = completion.choices[0].message.content
    state["english_poem"] = poem
    return state

def skill_translate_zh(state, params):
    text = state.get("english_poem", "")
    prompt = params.get("prompt") or f"翻译成中文诗：\n{text}"
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    zh = completion.choices[0].message.content
    state["chinese_poem"] = zh
    return state

SKILL_IMPL = {
    "generate_poem_en": skill_generate_poem_en,
    "translate_zh": skill_translate_zh,
}

def self_skills():
    for n in NODES:
        if n["id"] == SELF_ID:
            return set(n["skills"])
    return set()

SELF_SKILL_SET = self_skills()

# ====== 工具：根据 op 找一个有这个技能的节点 ======
def find_node_for_op(op):
    candidates = [n for n in NODES if op in n["skills"]]
    if not candidates:
        return None
    # 简单：随便选第一个，后面可以做负载均衡
    return candidates[0]

# ====== 接收完整任务（可以发给任意节点） ======
@app.route("/task", methods=["POST"])
def handle_task():
    # require user token
    token, err = _require_token(request)
    if err:
        return jsonify({'error': err[0]}), err[1]

    data = request.json or {}
    pipeline = data.get("pipeline")
    if not isinstance(pipeline, list):
        return jsonify({'error': 'pipeline missing or not a list'}), 400
    state = data.get("state", {})

    task_id = str(uuid.uuid4())
    TASK_STORE[task_id] = {'owner': token, 'pipeline': pipeline, 'final_state': None, 'status': 'running'}

    for step in pipeline:
        op = step["op"]
        params = step.get("params", {})

        # 如果调用方/AI 指定了 target_node 且该节点存在且声明了此技能，则优先使用
        specified = step.get("target_node")
        target_node = None
        if specified:
            for n in NODES:
                if n['id'] == specified and op in n.get('skills', []):
                    target_node = n
                    break

        # 否则按照能力选择节点
        if target_node is None:
            target_node = find_node_for_op(op)
        if target_node is None:
            return jsonify({"error": f"no node can handle op={op}"}), 400

        if target_node["id"] == SELF_ID:
            # 本机有这个技能 → 本地执行
            impl = SKILL_IMPL.get(op)
            if impl is None:
                return jsonify({"error": f"skill {op} not implemented on this node"}), 500
            state = impl(state, params)
        else:
            # 交给别的节点执行这一步
            url = target_node["url"] + "/execute_step"
            payload = {
                "op": op,
                "params": params,
                "state": state,
            }
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code != 200:
                return jsonify({"error": f"remote node {target_node['id']} failed", "detail": resp.text}), 500
            state = resp.json()["state"]

    # 保存并返回 task_id 与最终状态
    TASK_STORE[task_id]['final_state'] = state
    TASK_STORE[task_id]['status'] = 'done'
    return jsonify({"task_id": task_id, "final_state": state})

# ====== 只执行单个 step 的接口（给别的节点调用） ======
@app.route("/execute_step", methods=["POST"])
def execute_step():
    data = request.json
    op = data["op"]
    params = data.get("params", {})
    state = data.get("state", {})

    if op not in SELF_SKILL_SET:
        return jsonify({"error": f"this node cannot handle {op}"}), 400

    impl = SKILL_IMPL.get(op)
    if impl is None:
        return jsonify({"error": f"skill {op} not implemented in code"}), 500

    state = impl(state, params)
    return jsonify({"state": state})

# ====== 查看节点信息 ======
@app.route("/info", methods=["GET"])
def info():
    return jsonify({
        "id": SELF_ID,
        "url": SELF_URL,
        "skills": list(SELF_SKILL_SET),
    })


@app.route('/result/<task_id>', methods=['GET'])
def get_result(task_id):
    # 只有任务 owner 可以读取结果
    token, err = _require_token(request)
    if err:
        return jsonify({'error': err[0]}), err[1]
    t = TASK_STORE.get(task_id)
    if not t:
        return jsonify({'error': 'task not found'}), 404
    if t['owner'] != token:
        return jsonify({'error': 'forbidden'}), 403
    return jsonify({'task_id': task_id, 'status': t['status'], 'final_state': t.get('final_state')})


def _all_allowed_ops():
    """从 nodes.json 中收集所有声明的技能作为允许列表"""
    ops = set()
    for n in NODES:
        for s in n.get("skills", []):
            ops.add(s)
    return ops


def _extract_json_candidate(text: str):
    # 尝试直接 json.loads，否则尝试提取第一个花括号包围的 JSON
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # 找到第一个 { 到最后一个 } 的片段
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                return None
        return None


def _validate_tasks_structure(obj):
    # 期望 obj 为 { "tasks": [ {id, op, params, target_node?}, ... ] }
    if not isinstance(obj, dict):
        return False, 'response is not a JSON object'
    tasks = obj.get('tasks')
    if not isinstance(tasks, list):
        return False, 'tasks must be a list'

    allowed_ops = _all_allowed_ops()
    node_ids = {n['id'] for n in NODES}

    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            return False, f'task[{i}] is not an object'
        op = t.get('op')
        if not isinstance(op, str):
            return False, f'task[{i}].op missing or not a string'
        if op not in allowed_ops:
            return False, f'task[{i}].op "{op}" not in allowed operations'
        params = t.get('params', {})
        if not isinstance(params, dict):
            return False, f'task[{i}].params must be an object'
        target = t.get('target_node')
        if target is not None and target not in node_ids:
            return False, f'task[{i}].target_node "{target}" not a known node'

    return True, ''


@app.route('/analyze', methods=['POST'])
def analyze():
    """接受 { command: '...' }，调用 OpenAI 返回拆分任务的 JSON，验证并返回 tasks 列表"""
    data = request.json or {}
    command = data.get('command')
    if not command or not isinstance(command, str):
        return jsonify({'error': 'missing command'}), 400

    # 生成 prompt：强制模型仅返回 JSON，并且为每个 task 指定 target_node（必须是下面给出的节点 id 之一）
    allowed_ops = sorted(list(_all_allowed_ops()))
    node_ids = [n['id'] for n in NODES]
    prompt = (
        "You are an assistant that splits a user's high-level command into a sequence of small tasks.\n"
        "Return only a JSON object with the shape: { \"tasks\": [ { \"id\": string, \"op\": string, \"params\": object, \"target_node\": string }, ... ] }\n"
        "For each task, set \"target_node\" to one of the following node ids: " + ", ".join(node_ids) + ".\n"
        "Ensure that the chosen target_node actually supports the requested operation (i.e., its skills include the op).\n"
        "Use only these operations: " + ", ".join(allowed_ops) + ".\n"
        "Do not include any code, commands, or explanation text—only the JSON.\n"
        f"User command: {command}\n"
    )

    try:
        resp = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.0,
        )
    except Exception as e:
        return jsonify({'error': 'openai error', 'detail': str(e)}), 500

    # 尝试从模型输出中提取 JSON
    text = ''
    try:
        text = resp.choices[0].message.content
    except Exception:
        # fallback: convert to str
        text = str(resp)

    parsed = _extract_json_candidate(text)
    if parsed is None:
        return jsonify({'error': 'failed to parse JSON from model output', 'raw': text}), 502

    # 如果模型没有指定 target_node 或指定了不存在的 node，后端尝试填充一个可用的节点
    tasks = parsed.get('tasks') if isinstance(parsed, dict) else None
    if not isinstance(tasks, list):
        return jsonify({'error': 'parsed output missing tasks list', 'raw': parsed}), 502

    node_ids = {n['id'] for n in NODES}
    for t in tasks:
        op = t.get('op')
        specified = t.get('target_node')
        if specified and specified in node_ids:
            # 如果指定的节点存在，且后端会在后续校验检查该节点是否支持 op
            continue
        # 需要后端填充：找一个能够执行该 op 的节点
        chosen = find_node_for_op(op)
        if chosen:
            t['target_node'] = chosen['id']
        else:
            return jsonify({'error': f'no node can handle op={op}', 'raw': parsed}), 400

    # 现在对填充后的结构做一次严格校验
    ok, reason = _validate_tasks_structure({'tasks': tasks})
    if not ok:
        return jsonify({'error': 'invalid tasks structure after fill', 'detail': reason, 'raw': tasks}), 400

    # 成功：返回解析并校验后的 tasks（包含 target_node）
    return jsonify({'tasks': tasks, 'info': 'analyze successful'})

if __name__ == "__main__":
    # 两台电脑都用 0.0.0.0:5000，靠 IP 区分
    app.run(host="0.0.0.0", port=5000)
