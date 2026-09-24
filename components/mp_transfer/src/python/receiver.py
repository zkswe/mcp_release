#!/usr/bin/env python3
"""模拟相框接收端：UDP 8899 广播，TCP 9000 接收媒体。仅依赖 Python 标准库。

运行：python receiver.py --name PythonFrame
多网卡：python receiver.py --bind <本机IP> --broadcast <子网广播地址>
诊断：python receiver.py --verbose
停止：Ctrl+C
"""

import argparse
import logging
import math
import os
from pathlib import Path, PureWindowsPath
import socket
import struct
import sys
import tempfile
import threading
import time


UDP_PORT = 8899
TCP_PORT = 9000
CHUNK_SIZE = 32 * 1024
MAX_FILE_SIZE = 500 * 1024 * 1024
LOG = logging.getLogger("receiver")


class ProtocolError(Exception):
    pass


def recv_exact(conn, size, allow_eof=False):
    """按字段长度读取，兼容 TCP 拆包；仅在包头起点允许正常 EOF。"""
    data = bytearray()
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
        except socket.timeout as exc:
            raise TimeoutError(
                f"等待数据超时：当前字段/分块收到 {len(data)}/{size} 字节"
            ) from exc
        if not chunk:
            if allow_eof and not data:
                return None
            raise ProtocolError(f"对端中断：当前字段/分块收到 {len(data)}/{size} 字节")
        data.extend(chunk)
    return bytes(data)


def decode_filename(raw):
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("文件名不是有效 UTF-8") from exc
    if not name or ".." in name or any(c in name for c in "/\\\0"):
        raise ProtocolError(f"不合法的文件名：{name!r}")
    # Windows 的冒号、设备名等不能直接作为落盘文件名。
    if os.name == "nt" and (
        any(ord(c) < 32 or c in '<>:"|?*' for c in name)
        or name.endswith((" ", "."))
        or PureWindowsPath(name).is_reserved()
    ):
        raise ProtocolError(f"Windows 不支持此文件名：{name!r}")
    return name


def receive_file(conn, output_dir, name, size, packet_type):
    """文件内容分块落盘，非末块回复 ACK，改名成功后回复 OK。"""
    destination = output_dir / name
    if destination.is_symlink():
        raise ProtocolError(f"目标不能是符号链接：{name!r}")
    started = time.monotonic()
    received = 0
    last_progress = started
    LOG.info("开始接收 type=%d，文件=%r，大小=%d 字节", packet_type, name, size)

    # 随机临时文件避免与已完成文件冲突；只清理本次创建的临时文件。
    fd, temp_name = tempfile.mkstemp(prefix=".receiving-", suffix=".part", dir=output_dir)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            while received < size:
                data = recv_exact(conn, min(CHUNK_SIZE, size - received))
                if stream.write(data) != len(data):
                    raise OSError("文件写入不完整")
                received += len(data)
                if received < size:
                    conn.sendall(f"ACK {received}\n".encode("ascii"))
                    LOG.debug("发送 ACK %d", received)
                now = time.monotonic()
                if now - last_progress >= 1:
                    LOG.info("接收进度 %r：%.1f%% (%d/%d)", name, received * 100 / size, received, size)
                    last_progress = now

        if temporary.stat().st_size != size:
            raise OSError("落盘文件大小与包头不符")
        if destination.exists():
            LOG.warning("同名文件将覆盖：%s", destination)
        os.replace(temporary, destination)
        try:
            conn.sendall(b"OK\n")
        except OSError:
            LOG.error("文件已保存，但最终 OK 发送失败：%s", destination)
            raise
        elapsed = max(time.monotonic() - started, 0.001)
        LOG.info("接收成功，已发送 OK：%s (%.2f 秒，%.2f MiB/s)", destination, elapsed, size / elapsed / 1048576)
    finally:
        temporary.unlink(missing_ok=True)


def handle_client(conn, peer, output_dir):
    """一条连接可连续接收多个文件，不额外发送欢迎或握手报文。"""
    LOG.info("TCP 已连接：%s:%s", *peer[:2])
    while True:
        header = recv_exact(conn, 5, allow_eof=True)
        if header is None:
            LOG.info("对端正常关闭连接")
            return
        packet_type, size = struct.unpack("!BI", header)
        if not 0 < size <= MAX_FILE_SIZE:
            raise ProtocolError(f"无效内容长度：{size}，允许 1..{MAX_FILE_SIZE}")

        if packet_type == 0:
            # 保留 C++ 的文本兼容分支，流式消费，不解析业务命令。
            remaining = size
            while remaining:
                remaining -= len(recv_exact(conn, min(CHUNK_SIZE, remaining)))
            conn.sendall(b"OK\n")
            LOG.info("文本包接收完成：%d 字节，已发送 OK", size)
            continue
        if packet_type not in (1, 2, 3):
            raise ProtocolError(f"不支持的包类型：{packet_type}")

        name_size = struct.unpack("!H", recv_exact(conn, 2))[0]
        if not 1 <= name_size <= 256:
            raise ProtocolError(f"无效文件名长度：{name_size}")
        name = decode_filename(recv_exact(conn, name_size))
        receive_file(conn, output_dir, name, size, packet_type)


def broadcast_loop(udp, target, payload, stop):
    while not stop.is_set():
        try:
            udp.sendto(payload, target)
            LOG.debug("UDP 广播 → %s:%d，内容=%r", *target, payload)
        except OSError as exc:
            LOG.warning("UDP 广播失败：%s", exc)
        stop.wait(2)


def serve(args):
    output_dir = args.output.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server, \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        if os.name == "nt":
            server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.bind, TCP_PORT))
        server.listen(8)
        server.settimeout(0.5)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.bind((args.bind, 0))
        udp.settimeout(2)

        payload = ("zkswe:" + args.name).encode("utf-8")
        worker = threading.Thread(
            target=broadcast_loop,
            args=(udp, (args.broadcast, UDP_PORT), payload, stop),
            daemon=True,
        )
        LOG.info("TCP 监听 %s:%d，连接收发超时 %.1f 秒", args.bind, TCP_PORT, args.timeout)
        LOG.info("每 2 秒广播 %r → %s:%d", payload.decode("utf-8"), args.broadcast, UDP_PORT)
        LOG.info("文件保存目录：%s", output_dir)
        LOG.info("手机与电脑连接同一局域网，在小程序选择该设备。按 Ctrl+C 停止。")
        worker.start()
        try:
            while True:
                try:
                    conn, peer = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(args.timeout)
                    try:
                        handle_client(conn, peer, output_dir)
                    except (OSError, ProtocolError) as exc:
                        LOG.warning("本次连接结束：%s", exc)
        finally:
            stop.set()
            worker.join(timeout=3)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="PythonFrame", help="广播设备名称（默认 PythonFrame）")
    parser.add_argument("--bind", default="0.0.0.0", help="本机 IPv4；多网卡时指定与手机同网段的地址")
    parser.add_argument("--broadcast", default="255.255.255.255", help="广播目标 IPv4，可指定本地子网广播地址")
    parser.add_argument("--output", type=Path, default=Path("output/miniprogram_received"), help="接收目录，默认当前目录下 output/miniprogram_received；同名覆盖")
    parser.add_argument("--timeout", type=float, default=2.0, help="连接收发超时秒数，默认与 C++ 一致为 2；不是整文件限时")
    parser.add_argument("--verbose", action="store_true", help="打印每次广播和每个分块 ACK")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是大于 0 的有限数值")
    args.name = args.name.strip() or "Frame"
    if any(c in args.name for c in "\0\r\n") or len(("zkswe:" + args.name).encode("utf-8")) > 1024:
        parser.error("设备名不能含换行或 NUL，广播内容不能超过 1024 字节")
    for option in ("bind", "broadcast"):
        try:
            socket.inet_pton(socket.AF_INET, getattr(args, option))
        except OSError:
            parser.error(f"--{option} 必须是 IPv4 地址")
    return args


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        serve(args)
    except KeyboardInterrupt:
        LOG.info("已停止")
    except OSError as exc:
        LOG.error("启动或监听失败：%s；请检查本机 IP、端口占用和接收目录", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
