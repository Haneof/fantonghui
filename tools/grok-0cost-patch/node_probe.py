# -*- coding: utf-8 -*-
"""node_probe.py — 按「流水线真实需求」验活代理节点。

与常见免费节点测速脚本的区别：
  常见做法  : requests.get("http://1.1.1.1/cdn-cgi/trace", proxies=...)  -> 只验明文 HTTP
  本脚本    : CONNECT host:443 -> TLS 握手 -> 读真实出口 IP -> 可选验 x.ai 是否 403

因为 proxy_relay.py 走的是 CONNECT 隧道，大量免费 HTTP 代理不支持 CONNECT
或只放行 80 端口，用明文 HTTP 验活会产出一堆「测试通过、流水线必挂」的节点。

只用标准库，不需要 requests。

用法:
    python node_probe.py nodes1.txt nodes2.txt --out valid_proxies.txt
    python node_probe.py nodes.txt --xai            # 额外验 accounts.x.ai 是否 403
    python node_probe.py nodes.txt --limit 500 --workers 200
"""
import argparse
import base64
import concurrent.futures as cf
import io
import json
import os
import re
import socket
import ssl
import sys
import time

IPPORT_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}\b")
AUTH_RE = re.compile(r"\b([^\s:/@]+):([^\s:/@]+)@((?:\d{1,3}\.){3}\d{1,3}):(\d{1,5})\b")

TRACE_HOST = "www.cloudflare.com"
TRACE_PORT = 443
XAI_HOST = "accounts.x.ai"
XAI_PORT = 443


def parse_nodes(paths):
    """从 txt / json 里抽出节点。支持 ip:port 与 user:pass@ip:port。"""
    seen, out = set(), []
    for p in paths:
        if not os.path.isfile(p):
            print("[跳过] 不存在: %s" % p)
            continue
        raw = io.open(p, encoding="utf-8", errors="ignore").read()
        if p.lower().endswith(".json"):
            try:
                data = json.loads(raw)
                raw = json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
        n0 = len(out)
        for m in AUTH_RE.finditer(raw):
            u, pw, h, pt = m.groups()
            key = "%s:%s@%s:%s" % (u, pw, h, pt)
            if key not in seen:
                seen.add(key)
                out.append({"host": h, "port": int(pt), "user": u, "pw": pw, "raw": key})
        stripped = AUTH_RE.sub(" ", raw)
        for m in IPPORT_RE.finditer(stripped):
            hp = m.group(0)
            if hp in seen:
                continue
            h, pt = hp.rsplit(":", 1)
            try:
                pt = int(pt)
            except ValueError:
                continue
            if not (0 < pt < 65536):
                continue
            seen.add(hp)
            out.append({"host": h, "port": pt, "user": None, "pw": None, "raw": hp})
        print("[读取] %-34s -> 新增 %d 个" % (os.path.basename(p), len(out) - n0))
    return out


def _connect_tunnel(node, target_host, target_port, timeout):
    """建立 CONNECT 隧道，返回已连接的 socket。失败抛异常。"""
    s = socket.create_connection((node["host"], node["port"]), timeout=timeout)
    s.settimeout(timeout)
    req = "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n" % (
        target_host, target_port, target_host, target_port)
    if node.get("user"):
        tok = base64.b64encode(
            ("%s:%s" % (node["user"], node["pw"])).encode()).decode()
        req += "Proxy-Authorization: Basic %s\r\n" % tok
    req += "User-Agent: Mozilla/5.0\r\nProxy-Connection: Keep-Alive\r\n\r\n"
    s.sendall(req.encode())

    resp = b""
    while b"\r\n\r\n" not in resp:
        ch = s.recv(4096)
        if not ch:
            break
        resp += ch
        if len(resp) > 8192:
            break
    line = resp.split(b"\r\n")[0].decode("latin-1", "ignore")
    if " 200" not in line:
        s.close()
        raise OSError("CONNECT 被拒: %s" % (line[:60] or "无响应"))
    return s


def _https_get(sock, host, path, timeout):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ts = ctx.wrap_socket(sock, server_hostname=host)
    ts.settimeout(timeout)
    ts.sendall((
        "GET %s HTTP/1.1\r\nHost: %s\r\n"
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n"
        "Accept: */*\r\nConnection: close\r\n\r\n" % (path, host)).encode())
    buf = b""
    while len(buf) < 65536:
        try:
            ch = ts.recv(8192)
        except Exception:
            break
        if not ch:
            break
        buf += ch
    try:
        ts.close()
    except Exception:
        pass
    return buf.decode("utf-8", "ignore")


def probe(node, timeout=6, check_xai=False):
    """三段验证：CONNECT -> TLS+trace 取出口 IP -> (可选) x.ai 状态码。"""
    r = {"raw": node["raw"], "ok": False, "stage": "connect",
         "ip": None, "loc": None, "ms": None, "xai": None, "err": None}
    t0 = time.time()
    try:
        s = _connect_tunnel(node, TRACE_HOST, TRACE_PORT, timeout)
        r["stage"] = "tls"
        body = _https_get(s, TRACE_HOST, "/cdn-cgi/trace", timeout)
        if "ip=" not in body:
            raise OSError("隧道通但取不到 trace")
        for ln in body.splitlines():
            if ln.startswith("ip="):
                r["ip"] = ln[3:].strip()
            elif ln.startswith("loc="):
                r["loc"] = ln[4:].strip()
        if not r["ip"]:
            raise OSError("解析不出出口 IP")
        r["ok"] = True
        r["stage"] = "done"
        r["ms"] = int((time.time() - t0) * 1000)

        if check_xai:
            try:
                s2 = _connect_tunnel(node, XAI_HOST, XAI_PORT, timeout)
                head = _https_get(s2, XAI_HOST, "/sign-up", timeout).split("\r\n")[0]
                m = re.search(r"HTTP/[\d.]+\s+(\d{3})", head)
                r["xai"] = m.group(1) if m else "?"
            except Exception as e:
                r["xai"] = "ERR:" + type(e).__name__
    except Exception as e:
        r["err"] = "%s: %s" % (type(e).__name__, str(e)[:60])
        r["ms"] = int((time.time() - t0) * 1000)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="valid_proxies.txt")
    ap.add_argument("--report", default="probe_report.json")
    ap.add_argument("--workers", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=6.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--xai", action="store_true", help="额外验 accounts.x.ai 是否 403")
    args = ap.parse_args()

    nodes = parse_nodes(args.files)
    if args.limit:
        nodes = nodes[:args.limit]
    print("\n>>> 待测节点: %d 个 | 并发 %d | 超时 %.1fs | 验x.ai=%s\n"
          % (len(nodes), args.workers, args.timeout, args.xai))
    if not nodes:
        return 1

    good, t0, done = [], time.time(), 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(probe, n, args.timeout, args.xai): n for n in nodes}
        for f in cf.as_completed(futs):
            done += 1
            r = f.result()
            if r["ok"]:
                good.append(r)
                print("[+] %-24s ip=%-16s loc=%-3s %5dms%s"
                      % (r["raw"], r["ip"], r["loc"] or "?", r["ms"],
                         ("  xai=" + str(r["xai"])) if args.xai else ""))
            if done % 200 == 0:
                print("    ... 已测 %d/%d，存活 %d" % (done, len(nodes), len(good)))

    good.sort(key=lambda x: x["ms"])
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(
        "".join(g["raw"] + "\n" for g in good))
    io.open(args.report, "w", encoding="utf-8").write(
        json.dumps(good, ensure_ascii=False, indent=1))

    print("\n" + "=" * 62)
    print("总数 %d | CONNECT+TLS 存活 %d (%.2f%%) | 耗时 %.1fs"
          % (len(nodes), len(good), 100.0 * len(good) / max(1, len(nodes)),
             time.time() - t0))
    uniq = sorted({g["ip"] for g in good if g["ip"]})
    print("不同出口 IP: %d 个" % len(uniq))
    if args.xai:
        ok200 = [g for g in good if str(g["xai"]).startswith("2")]
        f403 = [g for g in good if str(g["xai"]) == "403"]
        print("x.ai 可访问(2xx): %d | 被拒(403): %d" % (len(ok200), len(f403)))
        if ok200:
            print("*** 可用于注册的节点 ***")
            for g in ok200:
                print("    %s  ip=%s loc=%s" % (g["raw"], g["ip"], g["loc"]))
    print("存活节点已写入: %s" % args.out)
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
