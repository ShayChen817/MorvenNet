// 简单前端逻辑：发送 /analyze 请求并显示拆分的子任务；若后端不可用，可使用 mock 数据

const analyzeBtn = document.getElementById('analyzeBtn');
const dispatchAllBtn = document.getElementById('dispatchAllBtn');
const commandEl = document.getElementById('command');
const tokenEl = document.getElementById('token');
const fileInput = document.getElementById('fileUpload');
const subtasksEl = document.getElementById('subtasks');
const logArea = document.getElementById('logArea');
const mockToggle = document.getElementById('mockToggle');

function log(msg) {
  const t = new Date().toLocaleTimeString();
  logArea.textContent += `[${t}] ${msg}\n`;
  logArea.scrollTop = logArea.scrollHeight;
}

async function readFileText() {
  const f = fileInput.files[0];
  if (!f) return null;
  return await f.text();
}

analyzeBtn.addEventListener('click', async () => {
  subtasksEl.innerHTML = '';
  const fileText = await readFileText();
  const command = (fileText && fileText.trim()) || commandEl.value.trim();
  if (!command) { alert('请先输入命令或上传文件'); return; }

  log('开始分析命令...');
  try {
    const useMock = mockToggle.checked;
    let respJson;
    if (useMock) {
      log('使用 Mock 响应（前端模拟）');
      respJson = mockAnalyze(command);
      await new Promise(r => setTimeout(r, 500));
    } else {
      const token = tokenEl.value.trim();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['X-User-Token'] = token;
      const r = await fetch('/analyze', {
        method: 'POST',
        headers,
        body: JSON.stringify({ command }),
      });
      if (!r.ok) throw new Error(`分析接口返回 ${r.status}`);
      respJson = await r.json();
    }

    renderSubtasks(respJson);
    log('分析完成');
    dispatchAllBtn.disabled = false;
  } catch (err) {
    log('分析失败：' + err);
    alert('分析失败：' + err);
  }
});

function renderSubtasks(data) {
  // 期望 data = { tasks: [ { id, op, params, target_node (可选) } ], info?: '' }
  subtasksEl.innerHTML = '';
  if (!data || !Array.isArray(data.tasks)) {
    subtasksEl.textContent = '没有检测到子任务（data.tasks 为空）';
    return;
  }

  data.tasks.forEach((t, idx) => {
    const card = document.createElement('div');
    card.className = 'task-card';
    // 保存原始任务对象，便于后续提交保留 target_node 等字段
    card.dataset.task = JSON.stringify(t);
    card.innerHTML = `
      <div class="task-header">任务 ${idx+1} — ${t.op} <span class="small">(目标：${t.target_node||'本地'})</span></div>
      <div class="task-body"><pre>${escapeHtml(JSON.stringify(t.params, null, 2))}</pre></div>
      <div class="task-actions">
        <button class="dispatch-single">派发</button>
        <span class="status">待处理</span>
      </div>
    `;
    const dispatchBtn = card.querySelector('.dispatch-single');
    const statusSpan = card.querySelector('.status');
    dispatchBtn.addEventListener('click', async () => {
      statusSpan.textContent = '派发中...';
      try {
        const useMock = mockToggle.checked;
        let result;
        if (useMock) {
          log(`Mock 派发任务 ${t.op}`);
          await new Promise(r=>setTimeout(r,700));
          result = { ok: true, result: { mock: 'ok', op:t.op } };
        } else {
          // 这里按后端约定调用 /task
          const token = tokenEl.value.trim();
          const headers = { 'Content-Type': 'application/json' };
          if (token) headers['X-User-Token'] = token;
          const r = await fetch('/task', {
              method: 'POST',
              headers,
              body: JSON.stringify({ op: t.op, params: t.params, state: {} }),
            });
            result = await r.json();
        }
        statusSpan.textContent = '已完成';
        log(`任务 ${t.op} 完成: ${JSON.stringify(result)}`);
      } catch (err) {
        statusSpan.textContent = '失败';
        log('派发失败：' + err);
      }
    });

    subtasksEl.appendChild(card);
  });
}

// 提交整个 pipeline 给后端 /task（一次性）
dispatchAllBtn.addEventListener('click', async () => {
  const tasks = Array.from(document.querySelectorAll('.task-card')).map((card, idx) => {
    // 优先使用当初 AI 返回并保存在 data-task 的完整任务对象（包含 target_node）
    try {
      const t = JSON.parse(card.dataset.task || '{}');
      return { op: t.op, params: t.params || {}, target_node: t.target_node };
    } catch(e) {
      // 兜底：从 DOM 恢复
      const opText = card.querySelector('.task-header').textContent || '';
      const pre = card.querySelector('.task-body pre').textContent;
      let params = {};
      try { params = JSON.parse(pre); } catch(e) { params = {}; }
      const op = opText.split('—')[1] ? opText.split('—')[1].trim().split(' ')[0] : `op${idx}`;
      return { op, params };
    }
  });

  if (!tasks.length) { alert('没有子任务可提交'); return; }
  const token = tokenEl.value.trim();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['X-User-Token'] = token;

  log('提交 pipeline 给后端 /task');
  try {
    const r = await fetch('/task', { method: 'POST', headers, body: JSON.stringify({ pipeline: tasks }) });
    const js = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(js));
    log('提交成功，task_id=' + js.task_id);
    alert('提交成功，task_id=' + js.task_id);
    // 显示 final_state（如果后端同步返回）
    if (js.final_state) {
      const en = js.final_state.english_poem || '(无)';
      const zh = js.final_state.chinese_poem || '(无)';
      document.getElementById('englishPoem').textContent = en;
      document.getElementById('chinesePoem').textContent = zh;
      log('final_state 已显示在页面');
    }
  } catch (err) {
    log('提交失败：' + err);
    alert('提交失败：' + err);
  }
});

function mockAnalyze(command) {
  // 返回示例结构：两个任务：生成英文诗（本地 nodeA），翻译成中文（nodeB）
  return {
    tasks: [
      {
        id: 't1',
        op: 'generate_poem_en',
        params: { prompt: `Generate an English poem about: ${command}` },
        target_node: 'nodeA'
      },
      {
        id: 't2',
        op: 'translate_zh',
        params: { text_var: 'english_poem' },
        target_node: 'nodeB'
      }
    ],
    info: 'mock拆分：生成英文诗 -> 翻译中文'
  };
}

function escapeHtml(s) {
  return s.replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'})[c]);
}

// 自动填充示例
commandEl.value = '请生成一首关于秋天的英文诗，然后把英文翻译成中文';
log('前端就绪（mock 默认开启）');
