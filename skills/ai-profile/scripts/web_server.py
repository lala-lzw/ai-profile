#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - PerfDog 模式轻量 Web 控制面板与后台 API 服务
提供免依赖的纯 Python 标准库 HTTP 服务 (127.0.0.1:8088)，支持浏览器端与 IDE 内嵌实时打标交互。
"""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from session_manager import SessionManager

mgr = SessionManager()

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AiProfile - PerfDog 控制面板</title>
<script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
<style>
  body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
</style>
</head>
<body class="p-6 flex justify-center items-center min-h-screen">
  <div class="w-full max-w-lg bg-[#161b22] border border-[#30363d] rounded-2xl p-6 shadow-2xl">
    <!-- 头部信息 -->
    <div class="flex justify-between items-center border-b border-[#30363d] pb-4 mb-5">
      <div>
        <h1 class="text-xl font-bold text-[#58a6ff] flex items-center gap-2">
          ⚡ AiProfile <span class="text-xs bg-[#238636] text-white px-2 py-0.5 rounded-full font-semibold">PerfDog 模式</span>
        </h1>
        <p id="devInfo" class="text-xs text-[#8b949e] mt-1">检测设备与前台中...</p>
      </div>
      <div id="statusBadge" class="text-xs font-bold px-3 py-1 rounded-full bg-[#21262d] text-[#8b949e]">
        ● 待机中
      </div>
    </div>

    <!-- 计时与核心控制 -->
    <div class="flex items-center justify-between bg-[#0d1117] border border-[#30363d] rounded-xl p-4 mb-5">
      <div>
        <div class="text-xs text-[#8b949e]">采样运行时长</div>
        <div id="timerText" class="text-2xl font-mono font-bold text-[#f0f6fc]">00:00.0</div>
      </div>
      <div class="flex gap-2">
        <button id="startBtn" onclick="doStart()" class="px-4 py-2.5 bg-[#238636] hover:bg-[#2ea043] active:bg-[#238636] text-white font-semibold text-sm rounded-lg shadow transition">
          ▶ 开始收集
        </button>
        <button id="stopBtn" onclick="doStop()" disabled class="px-4 py-2.5 bg-[#da3633] hover:bg-[#f85149] disabled:bg-[#21262d] disabled:text-[#484f58] text-white font-semibold text-sm rounded-lg shadow transition">
          ⏹ 结束收集
        </button>
      </div>
    </div>

    <!-- 打标签输入框 -->
    <div class="bg-[#0d1117] border border-[#30363d] rounded-xl p-4 mb-5">
      <div class="text-xs font-semibold text-[#58a6ff] mb-2 flex justify-between">
        <span>🏷️ 时间轴实时打标 (Marker)</span>
        <span class="text-[#8b949e] font-normal">支持直接回车</span>
      </div>
      <div class="flex gap-2">
        <input id="tagInput" type="text" placeholder="输入标签名 (如: 进副本, 团战爆发, 放技能)..." 
               onkeydown="if(event.key==='Enter') doAddTag()"
               class="flex-1 bg-[#161b22] border border-[#30363d] focus:border-[#58a6ff] outline-none text-sm text-[#c9d1d9] px-3 py-2 rounded-lg">
        <button id="tagBtn" onclick="doAddTag()" disabled class="px-4 py-2 bg-[#1f6feb] hover:bg-[#388bfd] disabled:bg-[#21262d] disabled:text-[#484f58] text-white font-medium text-sm rounded-lg transition">
          打标
        </button>
      </div>
      <!-- 快捷预设 -->
      <div class="flex flex-wrap gap-1.5 mt-3">
        <button onclick="quickTag('进入大世界')" class="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] px-2.5 py-1 rounded">进入大世界</button>
        <button onclick="quickTag('团战爆发')" class="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] px-2.5 py-1 rounded">团战爆发</button>
        <button onclick="quickTag('释放全屏绝招')" class="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] px-2.5 py-1 rounded">释放全屏绝招</button>
        <button onclick="quickTag('场景加载')" class="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] px-2.5 py-1 rounded">场景加载</button>
        <button onclick="quickTag('切换极高画质')" class="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] px-2.5 py-1 rounded">切换极高画质</button>
      </div>
    </div>

    <!-- 已打标签列表 -->
    <div>
      <div class="text-xs text-[#8b949e] font-medium mb-2 flex justify-between">
        <span>已记录标签列表 (<span id="tagCount">0</span>)</span>
        <span id="tempText" class="text-[#f0883e]">瞬时温度: --°C</span>
      </div>
      <div id="tagList" class="bg-[#0d1117] border border-[#30363d] rounded-xl p-2.5 h-36 overflow-y-auto font-mono text-xs space-y-1.5">
        <div class="text-[#484f58] text-center py-8">暂无标签，点击开始后输入标签名称记录</div>
      </div>
    </div>
  </div>

<script>
let isRunning = false;
let startTime = 0;
let pollTimer = null;

async function checkStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    document.getElementById('devInfo').innerText = `设备: ${data.device || '已连接'} | 前台: ${data.package || '检测中'}`;
    if (data.temp_c) {
      document.getElementById('tempText').innerText = `瞬时温度: ${data.temp_c.toFixed(1)}°C`;
    }
    if (data.active) {
      if (!isRunning) {
        isRunning = true;
        startTime = data.start_time;
        updateUIState(true);
      }
      renderLabels(data.labels || []);
    } else {
      if (isRunning) {
        isRunning = false;
        updateUIState(false);
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function updateUIState(active) {
  document.getElementById('startBtn').disabled = active;
  document.getElementById('stopBtn').disabled = !active;
  document.getElementById('tagBtn').disabled = !active;
  
  const badge = document.getElementById('statusBadge');
  if (active) {
    badge.innerText = '● 正在高频采样中';
    badge.className = 'text-xs font-bold px-3 py-1 rounded-full bg-[#238636] text-white animate-pulse';
  } else {
    badge.innerText = '● 待机中';
    badge.className = 'text-xs font-bold px-3 py-1 rounded-full bg-[#21262d] text-[#8b949e]';
  }
}

function renderLabels(labels) {
  document.getElementById('tagCount').innerText = labels.length;
  const list = document.getElementById('tagList');
  if (!labels.length) {
    list.innerHTML = '<div class="text-[#484f58] text-center py-8">暂无标签，点击开始后输入标签名称记录</div>';
    return;
  }
  list.innerHTML = labels.map(l => `
    <div class="flex items-center justify-between bg-[#161b22] px-2.5 py-1.5 rounded border border-[#21262d]">
      <span class="text-[#58a6ff] font-bold">🏷️ ${l.name}</span>
      <span class="text-[#8b949e]">+${l.time_s.toFixed(1)}s</span>
    </div>
  `).join('');
  list.scrollTop = list.scrollHeight;
}

async function doStart() {
  document.getElementById('startBtn').disabled = true;
  await fetch('/api/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tag: 'WebLiveSession'}) });
  checkStatus();
}

async function doAddTag() {
  const input = document.getElementById('tagInput');
  const text = input.value.trim();
  if (!text) return;
  await fetch('/api/mark', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: text}) });
  input.value = '';
  checkStatus();
}

function quickTag(text) {
  if (!isRunning) return;
  document.getElementById('tagInput').value = text;
  doAddTag();
}

async function doStop() {
  document.getElementById('stopBtn').disabled = true;
  document.getElementById('statusBadge').innerText = '⏳ 正在汇总生成报告...';
  const res = await fetch('/api/stop', { method: 'POST' });
  const data = await res.json();
  alert(`采样完成！总耗时 ${data.duration_s}s，记录标签 ${data.labels_count} 个。\\n即将打开走势图！`);
  if (data.html_url) {
    window.open(data.html_url, '_blank');
  }
  checkStatus();
}

setInterval(() => {
  if (isRunning && startTime > 0) {
    const elapsed = (Date.now() / 1000) - startTime;
    const mins = Math.floor(elapsed / 60);
    const secs = (elapsed % 60).toFixed(1);
    document.getElementById('timerText').innerText = 
      `${String(mins).padStart(2, '0')}:${String(secs).padStart(4, '0')}`;
  }
}, 100);

checkStatus();
setInterval(checkStatus, 1500);
</script>
</body>
</html>
"""

class AiProfileHandler(BaseHTTPRequestHandler):
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._set_cors()
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/status":
            session = mgr.get_current_session()
            t_c = 0.0
            try:
                t_res = mgr.adb.shell("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
                if t_res.ok and t_res.stdout.isdigit():
                    raw = float(t_res.stdout)
                    t_c = raw / 1000.0 if raw > 1000 else raw
            except Exception:
                pass

            data = {
                "active": bool(session and session.get("active")),
                "start_time": session.get("start_time", 0.0) if session else 0.0,
                "package": session.get("package", "") if session else (mgr.adb.get_foreground_app()[0] or ""),
                "device": session.get("device_env", {}).get("model", "") if session else (mgr.adb.prepare_device_env().get("model", "")),
                "labels": session.get("labels", []) if session else [],
                "temp_c": t_c
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._set_cors()
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif parsed.path.startswith("/report/"):
            # 允许查看生成的 timeline.html
            rel = parsed.path.replace("/report/", "")
            target_file = Path(rel)
            if target_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(target_file.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            body = json.loads(post_body)
        except Exception:
            body = {}

        parsed = urlparse(self.path)
        if parsed.path == "/api/start":
            tag = body.get("tag", "WebSession")
            pkg = body.get("package")
            try:
                s = mgr.start_session(package=pkg, tag=tag)
                resp = {"ok": True, "session": s}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._set_cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        elif parsed.path == "/api/mark":
            name = body.get("name", "Marker")
            try:
                m = mgr.add_marker(name)
                resp = {"ok": True, "marker": m}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._set_cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        elif parsed.path == "/api/stop":
            try:
                res = mgr.stop_session()
                html_url = f"/report/{res['timeline_html']}"
                resp = {
                    "ok": True,
                    "duration_s": res["duration_s"],
                    "labels_count": res["labels_count"],
                    "report_path": str(res["report_path"]),
                    "html_url": html_url
                }
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._set_cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))

def start_server(port: int = 8088):
    server = HTTPServer(("127.0.0.1", port), AiProfileHandler)
    print(f"[AiProfile] Web 控制面板已启动: http://127.0.0.1:{port}")
    server.serve_forever()

if __name__ == "__main__":
    start_server()
