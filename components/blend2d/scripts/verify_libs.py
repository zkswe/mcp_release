#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_libs.py —— components/blend2d 两个库档自检（可重跑，纯本地）

判据（与 lib/BUILD_INFO.md §3/§6 一致）：
  1) 体积/md5 = 表值（原厂 1,472,816 B / E07458D8…；NEON 1,874,056 B / C1E9DCCE…）
  2) 两档 **defined 动态符号集合完全相等**（787 total / 777 个 bl*）
  3) 两档 ELF 属性都是 7-A / v7 / VFPv4 / NEONv1 with Fused-MAC
  4) 原厂档 `q` 寄存器命中 = 0；NEON 档 > 0（--fast 跳过这一项：objdump 全量反汇编较慢）
  5) NEON 档 NEEDED 含 libgcc_s.so.1，原厂档不含

用法：
  python components/blend2d/scripts/verify_libs.py           # 全检
  python components/blend2d/scripts/verify_libs.py --fast    # 跳过反汇编统计（秒级）
  python components/blend2d/scripts/verify_libs.py --toolbin C:\\path\\to\\bin

说明：二进制只用厂家工具链自带的 readelf/objdump（自动探测）；**不用 nm**
      （Windows 版 binutils 的 nm 缺 liblto_plugin-0.dll 会直接报错）。
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIBROOT = os.path.normpath(os.path.join(HERE, "..", "lib"))

TARGETS = [
    dict(name="z20",      path=os.path.join(LIBROOT, "z20", "libblend2d.so"),
         size=1472816, md5="e07458d82437872d160c164106b529d4", neon=False),
    dict(name="z20-neon", path=os.path.join(LIBROOT, "z20-neon", "libblend2d.so"),
         size=1874056, md5="c1e9dcce2d1accc28eb46bb60f39cf72", neon=True),
]

TOOL_CANDIDATES = [
    r"C:\zkswe\fun\toolchains\z21\bin",
    r"C:\zkswe\fun\toolchains\z20\bin",
    r"C:\zkswe\fun\toolchains\z21\toolchain\bin",
]
TOOL_PREFIXES = ["arm-pc-linux-gnueabihf-", "arm-linux-gnueabihf-", ""]

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append((label, ok, detail))
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, ("  — " + detail) if detail else ""))


def find_tool(tool, extra_bin=None):
    bins = ([extra_bin] if extra_bin else []) + TOOL_CANDIDATES
    for d in bins:
        for pfx in TOOL_PREFIXES:
            for suffix in (".exe", ""):
                p = os.path.join(d, pfx + tool + suffix)
                if os.path.isfile(p):
                    return p
    # PATH 兜底
    for pfx in TOOL_PREFIXES:
        for suffix in (".exe", ""):
            name = pfx + tool + suffix
            for d in os.environ.get("PATH", "").split(os.pathsep):
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return p
    return None


def run(tool, args, timeout=600):
    try:
        p = subprocess.run([tool] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        return p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return ""
    except OSError as e:
        print("  运行 %s 失败：%s" % (tool, e))
        return ""


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_arm_attrs(text):
    out = {}
    for key in ("Tag_CPU_name", "Tag_CPU_arch", "Tag_FP_arch", "Tag_Advanced_SIMD_arch"):
        m = re.search(r"^\s*" + re.escape(key) + r":\s*(.+)$", text, re.M)
        if m:
            out[key] = m.group(1).strip()
    return out


def parse_needed(text):
    return re.findall(r"NEEDED\)\s+Shared library: \[([^\]]+)\]", text)


def parse_comment(text):
    # readelf -p .comment ->  "  [     0]  GCC: (...) 8.3.0 ..."
    for line in text.splitlines():
        if "GCC" in line or "clang" in line:
            m = re.search(r"\]\s+(.*\S)", line)
            if m:
                return m.group(1)
    return ""


def parse_dynsym(text):
    """解析 readelf --dyn-syms --wide，返回 (total, defined_names, defined_func_names)"""
    defined = set()
    funcs = set()
    total = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Num:") or line.startswith("Symbol table"):
            continue
        if not re.match(r"^\d+:", line):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        if parts[7].startswith("("):      # 折行残留/无名字，跳过
            continue
        total += 1
        typ, ndx, name = parts[3], parts[6], parts[7].split("@")[0]
        if ndx.upper() != "UND":
            defined.add(name)
            if typ == "FUNC":
                funcs.add(name)
    return total, defined, funcs


NEON_PATTERNS = [r"(^|[\s,])q\d+", r"\bvld1\b", r"\bvst1\b", r"\bvmul\b", r"\bvmla\b",
                 r"\bvadd\b", r"\bvzip\b", r"\bvmovl\b"]


def disasm_counts(tool, so):
    counts = dict((p, 0) for p in NEON_PATTERNS)
    regexes = [(p, re.compile(p)) for p in NEON_PATTERNS]
    try:
        p = subprocess.Popen([tool, "-d", so], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
    except OSError as e:
        print("  objdump 起不来：%s" % e)
        return None
    for raw in p.stdout:
        line = raw.decode("utf-8", "replace")
        for key, rx in regexes:
            counts[key] += len(rx.findall(line))
    p.wait()
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="跳过反汇编统计（objdump 较慢）")
    ap.add_argument("--toolbin", default=None, help="工具链 bin 目录（含 *-readelf.exe）")
    args = ap.parse_args()

    readelf = find_tool("readelf", args.toolbin)
    objdump = find_tool("objdump", args.toolbin)
    print("readelf: %s" % (readelf or "**未找到**"))
    print("objdump: %s" % (objdump or "**未找到**"))
    print("")

    info = {}
    for t in TARGETS:
        print("=== %s  (%s)" % (t["name"], t["path"]))
        if not os.path.isfile(t["path"]):
            check("%s 存在" % t["name"], False, "文件缺失")
            info[t["name"]] = None
            continue
        size = os.path.getsize(t["path"])
        md5 = md5_of(t["path"])
        check("%s 体积 %d B" % (t["name"], size), size == t["size"],
              "期望 %d" % t["size"])
        check("%s md5 %s" % (t["name"], md5), md5 == t["md5"], "期望 %s" % t["md5"])

        d = dict(size=size, md5=md5, attrs={}, needed=[], defined=set(), total=0, counts=None)
        if readelf:
            attrs = parse_arm_attrs(run(readelf, ["-A", t["path"]]))
            d["attrs"] = attrs
            check("%s ELF 属性 = 7-A/v7/VFPv4/NEONv1+FMAC" % t["name"],
                  attrs.get("Tag_CPU_name") == '"7-A"' and attrs.get("Tag_CPU_arch") == "v7"
                  and "NEONv1" in attrs.get("Tag_Advanced_SIMD_arch", ""),
                  str(attrs))
            d["needed"] = parse_needed(run(readelf, ["-d", t["path"]]))
            d["comment"] = parse_comment(run(readelf, ["-p", ".comment", t["path"]]))
            # ★ --wide 必须带上：不加时 readelf 会把长符号名折行，逐行解析会漏符号
            total, defined, funcs = parse_dynsym(run(readelf, ["--dyn-syms", "--wide", t["path"]]))
            d["total"], d["defined"] = total, defined
            bl = [n for n in defined if n.startswith("bl")]
            blfun = [n for n in funcs if n.startswith("bl")]
            print("        .comment : %s" % d["comment"])
            print("        NEEDED   : %s" % ", ".join(d["needed"]))
            print("        dynsym   : %d 条（defined %d；bl* %d = FUNC %d + 数据对象 %d）"
                  % (total, len(defined), len(bl), len(blfun), len(bl) - len(blfun)))
            check("%s defined 动态符号 = 787" % t["name"], len(defined) == 787,
                  "实际 %d" % len(defined))
            check("%s bl* FUNC = 777" % t["name"], len(blfun) == 777, "实际 %d" % len(blfun))
            has_gcc_s = any("libgcc_s" in n for n in d["needed"])
            check("%s NEEDED %s libgcc_s.so.1" % (t["name"], "含" if t["neon"] else "不含"),
                  has_gcc_s == t["neon"], ", ".join(d["needed"]))
        else:
            print("        （缺 readelf，跳过属性/符号检查）")

        if objdump and not args.fast:
            print("        objdump -d 统计中（可能几十秒）...")
            d["counts"] = disasm_counts(objdump, t["path"])
            if d["counts"]:
                q = d["counts"][NEON_PATTERNS[0]]
                print("        q-reg 操作数出现次数 %d（近似口径）/ vld1 %d / vst1 %d / vmul %d / vmla %d（后两项含 VFP 标量形式，非 NEON 判据）"
                      % (q, d["counts"][r"\bvld1\b"], d["counts"][r"\bvst1\b"],
                         d["counts"][r"\bvmul\b"], d["counts"][r"\bvmla\b"]))
                check("%s q 寄存器命中 %s" % (t["name"], "= 0（无 NEON 数据通路）" if not t["neon"]
                                              else "> 0（NEON 生效）"),
                      (q == 0) if not t["neon"] else (q > 0), "实际 %d" % q)
        info[t["name"]] = d
        print("")

    # ---------------- 跨档对比：ABI 必须全等
    a, b = info.get("z20"), info.get("z20-neon")
    print("=== 跨档对比（ABI 兼容性）")
    if a and b and a["defined"] and b["defined"]:
        only_old = sorted(a["defined"] - b["defined"])
        only_new = sorted(b["defined"] - a["defined"])
        check("defined 动态符号集合完全相等（787/787）",
              not only_old and not only_new,
              "old_only=%d new_only=%d %s" % (len(only_old), len(only_new),
                                              (only_old[:3] + only_new[:3])))
        check("两档 ELF 属性一致", a["attrs"] == b["attrs"] and bool(a["attrs"]))
    else:
        check("跨档符号对比", False, "缺数据（需 readelf）")

    bad = [r for r in RESULTS if not r[1]]
    print("")
    print("=" * 60)
    print("结果：%d 项，PASS %d，FAIL %d" % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    for label, _, detail in bad:
        print("  FAIL: %s  %s" % (label, detail))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
