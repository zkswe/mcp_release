#!/usr/bin/env python3
"""adb host-server 中转垫片：把 fun 发的旧式空格形式 transport 改写成冒号形式。

问题（2026-09-28 复核，fun 新旧版都一样）：
    fun launch 自带的 Go adb 客户端发的是 **`host:transport <serial>`（空格分隔）**，
    而 platform-tools（实测 37.0.1）只认 **`host:transport:<serial>`（冒号分隔）**：
    空格形式下 serial 被丢弃 → 只要 adb 列表里不止一台设备，就
    `FATAL "host:transport <serial>" FAIL: more than one device/emulator`。
    → 多设备在线时 `fun launch -s <IP>` 没法指定设备（单设备时靠 server 兜底才能过）。

本垫片做什么：
    监听 127.0.0.1:5037（fun 硬编码找的 adb host server 端口），把请求转发给
    真正跑在别的端口（默认 5038）的 adb server；只改写 transport 服务的分隔符，
    其余字节原样透传（sync:/shell: 之后切换成裸流透传）。

用法（两分钟，可逆）：
    adb kill-server
    adb -P 5038 start-server
    adb -P 5038 connect <ip>:5555            # 按需把设备连到 5038 这个 server 上
    python adb_transport_shim.py 5037 5038   # 垫片占住 5037
    fun launch -p <平台> -s <ip>:5555         # 现在多设备在线也能精确推到指定设备
    # 收尾
    <Ctrl-C> 停垫片; adb -P 5038 kill-server; adb start-server; adb connect ... （连回 5037）

实测（2026-09-28，本机 5 台 adb 在线；工程 DownloadTimerTest / Z20；设备 192.168.x.x）：
    `fun launch -p z20 -s 192.168.x.x:5555` → 4.02 s 推完（main.ftu + images + libzkgui.so + EasyUI.cfg），
    设备侧 md5 与本地构建产物逐一致（main.ftu = 本地 ui/main.ftu；libzkgui.so = 本地 .fsc/z20/libzkgui.so），
    另一台在线设备（192.168.x.x）**未被触碰**（无 /tmp/ui、lib 未变）。
    → 垫片是「多设备 + 指定设备推送」目前唯一不改厂家二进制就能走通的路子。

另一条路（不改任何东西）：让 adb 列表里只剩目标设备 —— `adb disconnect <其它 ip>:5555`
（网络设备可逆）或拔掉其它 USB，推完再连回。
"""
import io
import os
import socket
import sys
import tempfile
import threading
import time

LISTEN = int(sys.argv[1]) if len(sys.argv) > 1 else 5037
UPSTREAM = int(sys.argv[2]) if len(sys.argv) > 2 else 5038
LOG_PATH = os.environ.get('ADB_SHIM_LOG', os.path.join(tempfile.gettempdir(), 'adb_shim.log'))
VERBOSE = os.environ.get('ADB_SHIM_VERBOSE', '1') != '0'

# 这些服务发出去之后，连接会切成裸字节流（不再是 4 位十六进制长度前缀的帧）
RAW_AFTER = (b'sync:', b'shell:', b'exec:', b'reboot:', b'root:')

_log_fh = None
if VERBOSE:
    try:
        _log_fh = io.open(LOG_PATH, 'a', encoding='utf-8')
    except OSError:
        _log_fh = None


def log(msg):
    if _log_fh:
        _log_fh.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
        _log_fh.flush()
    if VERBOSE:
        sys.stderr.write(msg + '\n')
        sys.stderr.flush()


def recvn(sock, n):
    buf = b''
    while len(buf) < n:
        try:
            d = sock.recv(n - len(buf))
        except OSError as exc:
            log('recv error: %r' % exc)
            return None
        if not d:
            return None
        buf += d
    return buf


def client_to_server(csock, usock):
    try:
        while True:
            hdr = recvn(csock, 4)
            if hdr is None:
                return
            try:
                n = int(hdr, 16)
            except ValueError:
                log('bad frame header %r' % hdr)
                return
            payload = recvn(csock, n)
            if payload is None:
                return
            if payload.startswith(b'host:transport '):
                new = b'host:transport:' + payload[len(b'host:transport '):]
                log('REWRITE %r -> %r' % (payload, new))
                payload = new
            elif b'host:transport' in payload:
                log('PASS    %r' % (payload,))
            usock.sendall(('%04x' % len(payload)).encode() + payload)
            if payload.startswith(RAW_AFTER):
                log('RAW MODE after %r' % (payload,))
                while True:
                    try:
                        d = csock.recv(65536)
                    except OSError as exc:
                        log('raw error: %r' % exc)
                        return
                    if not d:
                        return
                    usock.sendall(d)
    except OSError as exc:
        log('c2s end: %r' % exc)
    finally:
        try:
            usock.shutdown(socket.SHUT_WR)
        except OSError as exc:
            log('c2s half-close failed (不影响主流程): %r' % exc)


def server_to_client(usock, csock):
    try:
        while True:
            d = usock.recv(65536)
            if not d:
                return
            csock.sendall(d)
    except OSError as exc:
        log('s2c end: %r' % exc)
    finally:
        try:
            csock.shutdown(socket.SHUT_WR)
        except OSError as exc:
            log('s2c half-close failed (不影响主流程): %r' % exc)


def handle(csock):
    try:
        usock = socket.create_connection(('127.0.0.1', UPSTREAM))
    except OSError as exc:
        log('upstream connect failed: %r' % exc)
        csock.close()
        return
    t1 = threading.Thread(target=client_to_server, args=(csock, usock), daemon=True)
    t2 = threading.Thread(target=server_to_client, args=(usock, csock), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    for s in (csock, usock):
        try:
            s.close()
        except OSError as exc:
            log('close failed (不影响主流程): %r' % exc)


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', LISTEN))
    srv.listen(32)
    log('adb transport shim listening %d -> %d (Ctrl-C 退出)' % (LISTEN, UPSTREAM))
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == '__main__':
    main()
