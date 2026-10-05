#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_lib_symbols.py -- 核对 lib/<平台>/libzkble.a 是否导出全部公开 API。

为什么不用 nm：Windows 版 binutils 的 nm 需要 liblto_plugin 插件，缺了就报错；
本脚本直接解析 ar + ELF（纯 Python，无外部依赖），任何机器上都能跑。

用法：
    python scripts/verify_lib_symbols.py                    # 检查组件内所有 lib/<平台>/libzkble.a
    python scripts/verify_lib_symbols.py --count <lib.a>    # 只打印某个 .a 的公开 API 命中数
退出码：0 = 全过；1 = 有缺失/文件缺失。
"""
import os
import struct
import sys

# 公开 API（与 include/zk/zk_ble.h 一一对应）——用"符号名子串"匹配，避开 C++ 名字修饰差异
PUBLIC_API = [
    # 适配器 / 能力
    "openAdapter", "closeAdapter", "adapterReady", "getAdapterState",
    "getCapabilities", "backendName", "setPreinitHook", "setLogHook",
    # 扫描
    "startDiscovery", "stopDiscovery", "getDevices", "clearDevices",
    # 连接 / 服务发现
    "connect", "disconnect", "isConnected", "getServices", "getCharacteristics",
    # 数据
    "readValue", "writeValue", "subscribe",
    # 配对
    "getBondedDevices", "deleteBonding",
    # 回调
    "onAdapterStateChange", "onDeviceFound", "onConnectionChange",
    "onValueChange", "onWriteRequest", "offAll",
    # 诊断 / 版本
    "getDiag", "version",
]
PERIPHERAL_API = ["start", "stop", "setDeviceName", "notify", "isConnected"]
# 透传管道（v0.3.0）：与后端无关，四平台都必须有
PIPE_API = ["listen", "connect", "send", "isConnected", "disconnect", "stop", "onData", "onState"]


def ns_api_hits(syms, ns, names):
    """名字空间级核对：要求「同一个符号里同时含 ns 与函数名」（避开子串误命中）"""
    hit = []
    for a in names:
        for s in syms:
            if ns in s and a in s:
                hit.append(a)
                break
    return hit


def read_ar_members(path):
    """Yields (name, bytes) for each member of a GNU ar archive."""
    with open(path, "rb") as f:
        magic = f.read(8)
        if magic != b"!<arch>\n":
            raise ValueError("not an ar archive: %s" % path)
        while True:
            hdr = f.read(60)
            if len(hdr) < 60:
                break
            name = hdr[0:16].decode("utf-8", "replace").strip()
            try:
                size = int(hdr[48:58].decode("ascii").strip() or "0")
            except ValueError:
                break
            data = f.read(size)
            if size % 2:                      # 成员按 2 字节对齐
                f.read(1)
            if name.endswith("/"):
                name = name[:-1]
            yield name, data


def elf_defined_symbols(blob):
    """Return set of defined global symbol names in an ELF object (or b'' if not ELF)."""
    if len(blob) < 64 or blob[0:4] != b"\x7fELF":
        return set()
    is64 = blob[4] == 2
    little = blob[5] == 1
    end = "<" if little else ">"
    if is64:
        e_shoff, = struct.unpack_from(end + "Q", blob, 0x28)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(end + "HHH", blob, 0x3A)
    else:
        e_shoff, = struct.unpack_from(end + "I", blob, 0x20)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(end + "HHH", blob, 0x2E)
    if not e_shoff or not e_shnum:
        return set()

    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        if is64:
            sh_type, = struct.unpack_from(end + "I", blob, off + 4)
            sh_offset, sh_size = struct.unpack_from(end + "QQ", blob, off + 0x18)
            sh_link, = struct.unpack_from(end + "I", blob, off + 0x28)
            sh_entsize, = struct.unpack_from(end + "Q", blob, off + 0x38)
        else:
            sh_type, = struct.unpack_from(end + "I", blob, off + 4)
            sh_offset, sh_size = struct.unpack_from(end + "II", blob, off + 0x10)
            sh_link, = struct.unpack_from(end + "I", blob, off + 0x18)
            sh_entsize, = struct.unpack_from(end + "I", blob, off + 0x24)
        sections.append({"type": sh_type, "off": sh_offset, "size": sh_size,
                         "link": sh_link, "entsize": sh_entsize})

    names = set()
    for sec in sections:
        if sec["type"] != 2:                  # SHT_SYMTAB
            continue
        strtab = sections[sec["link"]]
        strbase = strtab["off"]
        symsize = sec["entsize"] or (24 if is64 else 16)
        for k in range(sec["size"] // symsize):
            base = sec["off"] + k * symsize
            if is64:
                st_name, st_info, st_shndx = struct.unpack_from(end + "IBH", blob, base)
            else:
                st_name, = struct.unpack_from(end + "I", blob, base)
                st_info = blob[base + 12]
                st_shndx, = struct.unpack_from(end + "H", blob, base + 14)
            if st_shndx == 0:                 # SHN_UNDEF = 未定义（外部依赖）
                continue
            if (st_info >> 4) not in (1, 2):  # GLOBAL / WEAK
                continue
            end_pos = blob.find(b"\x00", strbase + st_name)
            if end_pos < 0:
                continue
            names.add(blob[strbase + st_name:end_pos].decode("utf-8", "replace"))
    return names


def lib_symbols(path):
    out = set()
    for name, blob in read_ar_members(path):
        out |= elf_defined_symbols(blob)
    return out


def check_one(path):
    syms = lib_symbols(path)
    allsym = " ".join(syms)
    missing = [a for a in PUBLIC_API if a not in allsym]
    peri = ns_api_hits(syms, "peripheral", PERIPHERAL_API)
    pipe = ns_api_hits(syms, "pipe", PIPE_API)
    return syms, missing, peri, pipe


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    comp = os.path.dirname(here)                      # components/ble
    if len(sys.argv) >= 3 and sys.argv[1] == "--count":
        _, missing, _, _ = check_one(sys.argv[2])
        print(max(0, len(PUBLIC_API) - len(missing)))
        return 0

    libroot = os.path.join(comp, "lib")
    if not os.path.isdir(libroot):
        print("FAIL: 找不到 %s" % libroot)
        return 1

    plats = sorted([d for d in os.listdir(libroot)
                    if os.path.isdir(os.path.join(libroot, d))])
    if not plats:
        print("FAIL: %s 下没有平台目录" % libroot)
        return 1

    bad = 0
    for p in plats:
        lib = os.path.join(libroot, p, "libzkble.a")
        if not os.path.isfile(lib):
            print("[FAIL] %-6s 缺 libzkble.a" % p)
            bad += 1
            continue
        syms, missing, peri, pipe = check_one(lib)
        ok = (not missing) and len(peri) == len(PERIPHERAL_API) and len(pipe) == len(PIPE_API)
        print("[%s] %-6s .a=%.0fKB 公开 API %d/%d%s%s%s" % (
            "PASS" if ok else "FAIL", p, os.path.getsize(lib) / 1024.0,
            len(PUBLIC_API) - len(missing), len(PUBLIC_API),
            "" if not missing else " 缺: " + ",".join(missing),
            "" if len(peri) == len(PERIPHERAL_API) else " 缺外设: " + ",".join(
                set(PERIPHERAL_API) - set(peri)),
            "" if len(pipe) == len(PIPE_API) else " 缺pipe: " + ",".join(
                set(PIPE_API) - set(pipe))))
        if not ok:
            bad += 1

    print("total=%d fail=%d" % (len(plats), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
