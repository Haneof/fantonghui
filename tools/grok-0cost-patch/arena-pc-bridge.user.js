// ==UserScript==
// @name         Arena 会话 → Windows 本地电脑控制桥（GPT PC Bridge）
// @namespace    https://github.com/fantonghui/chatgpt-pc-bridge
// @version      1.6.1
// @description  监听 arena.ai 会话中新出现的执行标记代码块，把命令发到本地 Bridge 执行。结果带 SHA 关联ID/序号/耗时，可与发出的指令逐条对账。
// @author       fantonghui
// @match        https://arena.ai/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ---------------------------------------------------------------- 配置
  const CFG = {
    BRIDGE_URL: GM_getValue('bridgeUrl', 'http://127.0.0.1:18765/execute'),
    TIMEOUT_MS: GM_getValue('timeoutMs', 180000),
    // 标记运行时拼装，源码中不出现连续字面量，避免脚本自身被误识别
    BEGIN: '###GPTPC' + '_BEGIN###',
    END: '###GPTPC' + '_END###',
    RESULT_HEADER: '【GPT PC AGENT 本地执行结果】',
    RESCAN_MS: 1500,        // 兜底轮询：防止 MutationObserver 漏帧
    IGNORE_FIRST_MS: 2500,  // 启动初期出现的块视为历史，不执行
  };

  // 占位符 / 非真实命令：命中即拒绝（保留，这类误伤率低）
  const PLACEHOLDER_RE = /(这里写命令|你的命令|真实命令|待填写|请输入|占位符|TODO|你的电脑|<command>|\[command\]|\{command\})/;

  // 真正「坏掉」的命令：只保留高置信度特征。
  // 注意：v1.4.2 里的 \.\.\. 和 \\n|\\r|\\t 已移除——
  //   - "..." 在中文文案和 Python 里极常见
  //   - Windows 路径 D:\report / D:\new / D:\temp 天然含 \r \n \t，全是误伤
  const BROKEN_RE = /^(cmd|dir|test|测试|\.\.\.|<|>)$/i;

  // 疑似被 JSON/HTML 转义搞坏：反斜杠转义 + 转义引号同时出现才算数
  function looksMangled(cmd) {
    return /\\[nrt]/.test(cmd) && /\\"/.test(cmd) && !cmd.includes('\n');
  }

  const startedAt = Date.now();
  const seenBlocks = new WeakSet();
  const inFlight = new Set();
  let lastResultText = '';
  let busy = 0;
  let seq = 0;
  const seenIds = new Map(); // sha8 -> 本次会话执行次数

  // 跨页面刷新持久化「已执行过的命令 ID」。
  // v1.6.0 靠 2.5s 时间窗判定历史块，渲染慢一点老命令就会真的重跑，
  // 而新命令又可能被误当历史吞掉（PING 就是这么丢的）。改用 ID 去重。
  let executedIds = new Set();
  try { executedIds = new Set(JSON.parse(GM_getValue('executedIds', '[]'))); } catch (e) {}
  function markExecuted(id) {
    executedIds.add(id);
    const arr = Array.from(executedIds).slice(-300);
    executedIds = new Set(arr);
    try { GM_setValue('executedIds', JSON.stringify(arr)); } catch (e) {}
  }

  async function sha8(text) {
    try {
      const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
      return Array.from(new Uint8Array(buf)).slice(0, 4)
        .map((b) => b.toString(16).padStart(2, '0')).join('');
    } catch (e) {
      // 非安全上下文没有 crypto.subtle，退回简易 hash
      let h = 0x811c9dc5;
      for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
      return h.toString(16).padStart(8, '0');
    }
  }

  function stamp() {
    const d = new Date(), z = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()) + ' '
      + z(d.getHours()) + ':' + z(d.getMinutes()) + ':' + z(d.getSeconds());
  }

  const log = (...a) => console.log('%c[PC-Bridge]', 'color:#4ade80', ...a);
  const warn = (...a) => console.warn('[PC-Bridge]', ...a);

  // ---------------------------------------------------------------- UI
  let panel, statusDot, statusText, bodyEl, copyBtn;

  function buildUI() {
    panel = document.createElement('div');
    panel.style.cssText = [
      'position:fixed', 'right:16px', 'bottom:16px', 'z-index:2147483647',
      'width:420px', 'max-height:52vh', 'display:flex', 'flex-direction:column',
      'background:#12161c', 'color:#e6edf3', 'border:1px solid #2d333b',
      'border-radius:10px', 'box-shadow:0 8px 28px rgba(0,0,0,.5)',
      'font:12px/1.5 Consolas,Menlo,monospace', 'overflow:hidden',
    ].join(';');

    const head = document.createElement('div');
    head.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 10px;background:#181d24;border-bottom:1px solid #2d333b;cursor:move';
    statusDot = document.createElement('span');
    statusDot.style.cssText = 'width:9px;height:9px;border-radius:50%;background:#4ade80;flex:none';
    statusText = document.createElement('span');
    statusText.textContent = 'PC Bridge 就绪';
    statusText.style.cssText = 'flex:1;font-weight:600';

    copyBtn = mkBtn('复制', () => {
      if (!lastResultText) return toast('没有可复制的内容', '#f59e0b');
      writeClipboard(lastResultText, true);
    });
    const clrBtn = mkBtn('清空', () => { bodyEl.textContent = ''; lastResultText = ''; });
    const minBtn = mkBtn('—', () => {
      const hidden = bodyEl.style.display === 'none';
      bodyEl.style.display = hidden ? 'block' : 'none';
      minBtn.textContent = hidden ? '—' : '+';
    });

    head.append(statusDot, statusText, copyBtn, clrBtn, minBtn);

    bodyEl = document.createElement('div');
    bodyEl.style.cssText = 'padding:8px 10px;overflow:auto;white-space:pre-wrap;word-break:break-all;flex:1;user-select:text';

    panel.append(head, bodyEl);
    document.body.appendChild(panel);
    makeDraggable(panel, head);
  }

  function mkBtn(label, fn) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = 'background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px;padding:2px 8px;cursor:pointer;font:11px/1.4 inherit';
    b.onmouseenter = () => (b.style.background = '#30363d');
    b.onmouseleave = () => (b.style.background = '#21262d');
    b.onclick = fn;
    return b;
  }

  function makeDraggable(el, handle) {
    let sx, sy, ox, oy, on = false;
    handle.addEventListener('mousedown', (e) => {
      if (e.target.tagName === 'BUTTON') return;
      on = true; sx = e.clientX; sy = e.clientY;
      const r = el.getBoundingClientRect(); ox = r.left; oy = r.top;
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!on) return;
      el.style.left = ox + e.clientX - sx + 'px';
      el.style.top = oy + e.clientY - sy + 'px';
      el.style.right = 'auto'; el.style.bottom = 'auto';
    });
    document.addEventListener('mouseup', () => (on = false));
  }

  function setStatus(text, color) {
    if (!statusText) return;
    statusText.textContent = text;
    statusDot.style.background = color || '#4ade80';
  }

  function append(text, color) {
    if (!bodyEl) return;
    const d = document.createElement('div');
    d.textContent = text;
    if (color) d.style.color = color;
    d.style.marginBottom = '6px';
    bodyEl.appendChild(d);
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function toast(msg, color) {
    append('• ' + msg, color || '#9ca3af');
  }

  // 历史里没跑过的命令：不自动执行，挂一个按钮让用户决定
  function addPending(id, cmd) {
    const row = document.createElement('div');
    row.style.cssText = 'margin-bottom:6px;padding:6px;border:1px dashed #4b5563;border-radius:6px';
    const t = document.createElement('div');
    t.textContent = '⏸ [' + id + '] 历史中未执行的命令 (' + cmd.length + ' 字符)';
    t.style.color = '#fbbf24';
    const pre = document.createElement('div');
    pre.textContent = cmd.slice(0, 160) + (cmd.length > 160 ? ' …' : '');
    pre.style.cssText = 'color:#6b7280;margin:4px 0';
    const run = mkBtn('▶ 执行', async () => { row.remove(); await execute(id, cmd); });
    const skip = mkBtn('忽略', () => { markExecuted(id); row.remove(); });
    row.append(t, pre, run, document.createTextNode(' '), skip);
    bodyEl.appendChild(row);
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  // ---------------------------------------------------------------- 剪贴板
  function writeClipboard(text, manual) {
    const ok = () => { setStatus('结果已复制到剪贴板', '#4ade80'); if (manual) toast('已复制', '#4ade80'); };
    const fail = (e) => {
      warn('剪贴板写入失败：', e);
      setStatus('剪贴板失败 — 请点「复制」按钮', '#f59e0b');
      toast('剪贴板写入失败（页面可能未聚焦）。结果已显示在下方，点标题栏「复制」可重试。', '#f59e0b');
      // 页面重新获得焦点时自动重试一次
      window.addEventListener('focus', function retry() {
        window.removeEventListener('focus', retry);
        navigator.clipboard && navigator.clipboard.writeText(text).then(ok).catch(() => {});
      });
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(ok).catch(() => legacyCopy(text) ? ok() : fail('execCommand 也失败'));
    } else {
      legacyCopy(text) ? ok() : fail('浏览器不支持 clipboard API');
    }
  }

  function legacyCopy(text) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      const r = document.execCommand('copy');
      document.body.removeChild(ta);
      return r;
    } catch (e) { return false; }
  }

  // ---------------------------------------------------------------- 命令校验
  function validate(cmd) {
    if (!cmd) return '空命令';
    if (cmd.length < 3) return '命令过短（<3 字符）';
    if (BROKEN_RE.test(cmd)) return '疑似占位命令：' + cmd;
    const p = cmd.match(PLACEHOLDER_RE);
    if (p) return '命中占位符关键词：' + p[0];
    if (looksMangled(cmd)) return '命令疑似被转义破坏（同时含 \\n 与 \\"）';
    return null; // 通过
  }

  // ---------------------------------------------------------------- 提取
  function extract(block) {
    const t = (block.textContent || '').trim();
    if (!t.startsWith(CFG.BEGIN)) return null;
    const inner = t.slice(CFG.BEGIN.length);
    const idx = inner.lastIndexOf(CFG.END);
    if (idx === -1) return null; // 还在流式输出中，结束标记未到
    let cmd = inner.slice(0, idx).trim()
      .replace(/^\s*```[\w-]*\s*/, '')
      .replace(/\s*```\s*$/, '')
      .trim();
    return cmd;
  }

  // ---------------------------------------------------------------- 执行
  function runCommand(cmd) {
    return new Promise((resolve) => {
      GM_xmlhttpRequest({
        method: 'POST',
        url: CFG.BRIDGE_URL,
        headers: { 'Content-Type': 'application/json' },
        data: JSON.stringify({ command: cmd }),
        timeout: CFG.TIMEOUT_MS,
        onload: (res) => {
          let p = null;
          try { p = JSON.parse(res.responseText); } catch (_) {}
          resolve(p
            ? { stdout: p.stdout ?? p.output ?? '', stderr: p.stderr ?? p.error ?? '', code: p.code ?? p.status ?? p.exit_code ?? null }
            : { stdout: res.responseText, stderr: '', code: null });
        },
        onerror: (err) => resolve({
          stdout: '', code: -1,
          stderr: '无法连接本地 Bridge：' + ((err && err.error) || '未知错误')
            + '\n请确认 C:\\ChatGPT-Bridge 服务已启动，且允许来自 https://arena.ai 的跨域请求。',
        }),
        ontimeout: () => resolve({ stdout: '', stderr: '本地 Bridge 请求超时（' + (CFG.TIMEOUT_MS / 1000) + 's）。', code: -2 }),
      });
    });
  }

  function present(cmd, r, meta) {
    const lines = [
      CFG.RESULT_HEADER,
      'id=' + meta.id + '  seq=' + meta.seq + '  耗时=' + meta.dur + 's  发出=' + meta.sent
        + '  命令长度=' + cmd.length + (meta.repeat > 1 ? '  [第' + meta.repeat + '次执行同一命令]' : ''),
      '',
      '命令:', cmd, '',
      '状态码: ' + (r.code === null ? '(未提供)' : r.code),
    ];
    if (r.stdout) lines.push('', 'stdout:', r.stdout.trim());
    if (r.stderr) lines.push('', 'stderr:', r.stderr.trim());
    lastResultText = lines.join('\n');

    append('◀ [' + meta.id + '] 完毕 · ' + meta.dur + 's · 状态码 '
      + (r.code === null ? '未提供' : r.code), r.code ? '#f87171' : '#4ade80');
    if (r.stdout) append(r.stdout.trim().slice(0, 4000), '#d1d5db');
    if (r.stderr) append(r.stderr.trim().slice(0, 4000), '#f87171');

    writeClipboard(lastResultText, false);
    log('执行结果:\n' + lastResultText);
  }

  // ---------------------------------------------------------------- 调度
  async function execute(id, cmd) {
    if (inFlight.has(cmd)) return;
    inFlight.add(cmd);
    busy++;

    const repeat = (seenIds.get(id) || 0) + 1;
    seenIds.set(id, repeat);
    const meta = { id: id, seq: ++seq, sent: stamp(), repeat: repeat };
    const t0 = performance.now();

    setStatus('执行中 [' + id + '] (' + busy + ')', '#60a5fa');
    append('▶ [' + id + '] seq=' + meta.seq + ' 发送 ' + cmd.length + ' 字符'
      + (repeat > 1 ? ' (重复第' + repeat + '次)' : ''), '#60a5fa');
    log('发送命令 id=' + id + ' seq=' + meta.seq + ':', cmd);

    const r = await runCommand(cmd);

    meta.dur = ((performance.now() - t0) / 1000).toFixed(1);
    inFlight.delete(cmd);
    busy--;
    markExecuted(id);
    present(cmd, r, meta);
    if (busy === 0 && statusText.textContent.startsWith('执行中')) setStatus('PC Bridge 就绪', '#4ade80');
  }

  async function consider(block) {
    if (seenBlocks.has(block)) return;

    const cmd = extract(block);
    if (cmd === null) return;      // 不是命令块，或还在流式输出 —— 不标记，留待重扫
    seenBlocks.add(block);

    const bad = validate(cmd);
    if (bad) {
      warn('命令被拒绝：' + bad + '\n' + cmd);
      setStatus('命令被拒绝', '#f87171');
      append('✕ 命令被拒绝：' + bad, '#f87171');
      append(cmd.slice(0, 300), '#6b7280');
      return;
    }

    const id = await sha8(cmd);

    if (executedIds.has(id)) { log('跳过已执行过的命令 id=' + id); return; }

    // 启动窗口内出现 = 页面刷新带出来的历史。不自动跑，但也不丢弃。
    if (Date.now() - startedAt < CFG.IGNORE_FIRST_MS) { addPending(id, cmd); return; }

    await execute(id, cmd);
  }

  function scanAll(root) {
    const scope = root && root.querySelectorAll ? root : document;
    for (const b of scope.querySelectorAll('pre, code')) consider(b);
  }

  // v1.4.2 的 collectCodeBlocks 对 ELEMENT_NODE 只向下搜、不向上找，
  // 流式渲染往 <code> 里插 <span> 时会整条漏掉。这里两个方向都走。
  function handleMutationNode(node) {
    if (node.nodeType === Node.ELEMENT_NODE) {
      if (node.closest) { const up = node.closest('pre, code'); if (up) consider(up); }
      scanAll(node);
    } else if (node.parentElement && node.parentElement.closest) {
      const up = node.parentElement.closest('pre, code');
      if (up) consider(up);
    }
  }

  // ---------------------------------------------------------------- 启动
  function start() {
    buildUI();
    log('v1.6.1 已加载，Bridge =', CFG.BRIDGE_URL);

    let baseline = 0;
    for (const b of document.querySelectorAll('pre, code')) { seenBlocks.add(b); baseline++; }
    append('PC Bridge v1.6.1 已就绪 · 忽略历史代码块 ' + baseline + ' 个', '#6b7280');

    new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === 'childList') m.addedNodes.forEach(handleMutationNode);
        else if (m.type === 'characterData') handleMutationNode(m.target);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });

    // 兜底轮询：任何被 observer 漏掉的块，最迟 1.5s 后也会被捡起来
    setInterval(() => scanAll(document), CFG.RESCAN_MS);

    if (typeof GM_registerMenuCommand === 'function') {
      GM_registerMenuCommand('设置 Bridge 地址', () => {
        const v = prompt('Bridge 地址', CFG.BRIDGE_URL);
        if (v) { GM_setValue('bridgeUrl', v); CFG.BRIDGE_URL = v; toast('已保存：' + v, '#4ade80'); }
      });
      GM_registerMenuCommand('设置超时(秒)', () => {
        const v = parseInt(prompt('超时秒数', CFG.TIMEOUT_MS / 1000), 10);
        if (v > 0) { GM_setValue('timeoutMs', v * 1000); CFG.TIMEOUT_MS = v * 1000; toast('已保存：' + v + 's', '#4ade80'); }
      });
    }
  }

  if (document.body) start();
  else window.addEventListener('DOMContentLoaded', start);
})();
