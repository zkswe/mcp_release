# -*- coding: utf-8 -*-
"""deploy.py — 把本 example 整包部署到 Z21（扁平布局：ui/ + .fun/z21/ + resources/）。

姿势（与项目里其它案例一致）：reboot -> 一次推完 -> kill zkgui 让 init respawn。
本 example **没有图片资源**（全部 ZKPainter 自绘），所以只推 lib + ftu + 工具。
用法：python tools/deploy.py [--no-reboot]
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # example 根
# 本机路径 / 设备地址一律走环境变量，仓库里不留内网 IP 与本机绝对路径（隐私扫描会拦）
def _resolve_adb():
    """adb 路径：环境变量 ADB → 随包 tools/adb/adb.exe → PATH（v0.27.84 统一入口）。

    优先复用仓库根的 adb_tools.resolve_adb()；本文件被单独拷走时退化到旧行为。"""
    env = os.environ.get('ADB') or os.environ.get('FLYTHINGS_ADB')
    if env and os.path.isfile(env):
        return env
    cur = HERE
    for _ in range(6):                      # 向上找仓库根的 adb_tools.py
        if os.path.isfile(os.path.join(cur, 'adb_tools.py')):
            if cur not in sys.path:
                sys.path.insert(0, cur)
            try:
                import adb_tools as _at
                p = _at.resolve_adb()
                if p:
                    return p
            except Exception:
                break
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.environ.get('ADB') or 'adb'


ADB = _resolve_adb()                                     # 可用 ADB=<adb 完整路径> 覆盖
BIN_TOOLS = os.environ.get('BIN_TOOLS', '')              # 例：指向 bin_tools/z21（含 touch/busybox）
DEV = os.environ.get('DEV', '192.168.1.100:5555')        # 改成你设备的 IP:PORT

CFG = {
    "baud": "115200", "defBrightness": -1,
    "languageCode": "zh_CN", "languagePath": "/tmp/tr/",
    "resPath": "/tmp/ui/", "rotateScreen": 0, "rotateTouch": 0,
    "screensaverTimeout": -1,
    "startupLibPath": "/tmp/lib/libzkgui.so", "startupTouchCalib": False,
    "touchDev": "/dev/input/event0", "uart": "ttyS1", "zkdebug": True,
}


def run(args, **kw):
    kw.setdefault('capture_output', True)
    kw.setdefault('text', True)
    kw.setdefault('encoding', 'utf-8')
    kw.setdefault('errors', 'replace')
    return subprocess.run(args, **kw)


def adb(*args):
    return run([ADB, '-s', DEV] + list(args))


def sh(cmd):
    return adb('shell', cmd)


def _restart_app(pid):
    """温和终止优先：`kill -TERM` → 等退出 → 仍在则回退 `kill -KILL`（init 会自动 respawn）。

    为什么不直接 `kill -9`（v0.27.90）：现场多次 `kill -9 zkgui` 之后（以及 reboot 之后）
    出现过整板掉网，**因果未定**（两条现象互相矛盾），所以只做无害的「优先温和」。
    实现优先复用仓库 `adb_tools.restart_app()`（单一实现）；本文件被单独拷走时用等价的内联逻辑。
    """
    try:
        cur = HERE
        for _ in range(6):
            if os.path.isfile(os.path.join(cur, 'adb_tools.py')):
                if cur not in sys.path:
                    sys.path.insert(0, cur)
                import adb_tools as _at
                r = _at.restart_app(ADB, DEV, 'zkgui')
                print('    adb_tools.restart_app: %s' % r['detail'])
                return
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    except Exception as e:
        print('    adb_tools.restart_app 不可用（%s），用内联温和终止' % e)
    sh('kill -TERM ' + pid)
    for _ in range(6):                       # 3s 内自己退出就不动 -KILL
        time.sleep(0.5)
        still = (sh('/tmp/busybox pidof zkgui').stdout or '').strip()
        if not still:
            print('    kill -TERM %s；已自行退出（未用 -KILL）' % pid)
            return
    sh('kill -KILL ' + pid)
    print('    kill -TERM %s；3s 内未退出 → 回退 kill -KILL' % pid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-reboot', action='store_true')
    a = ap.parse_args()

    so = os.path.join(HERE, '.fun', 'z21', 'libzkgui.so')
    ui = os.path.join(HERE, 'ui')
    ftu = os.path.join(ui, 'main.ftu')
    for p in (so, ftu):
        if not os.path.exists(p):
            print('missing: %s（先 fun build -p Z21）' % p)
            sys.exit(1)

    if not a.no_reboot:
        print('[0] reboot')
        adb('reboot')
        time.sleep(8)
        for _ in range(12):
            run([ADB, 'connect', DEV])
            if 'up' in (run([ADB, '-s', DEV, 'shell', 'echo', 'up']).stdout or ''):
                break
            time.sleep(5)
        time.sleep(3)

    sh('mkdir -p /tmp/ui /tmp/lib /tmp/tr')
    cfg = os.path.join(HERE, 'evidence', 'EasyUI.cfg')
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with io.open(cfg, 'w', encoding='utf-8') as f:
        f.write(json.dumps(CFG, ensure_ascii=False, indent=4))
    adb('push', cfg, '/tmp/EasyUI.cfg')
    adb('push', so, '/tmp/lib/libzkgui.so')
    adb('push', ftu, '/tmp/ui/main.ftu')
    print('[1] cfg + lib + ftu pushed')
    for tool in ('busybox', 'touch'):
        p = os.path.join(BIN_TOOLS, tool)
        if os.path.exists(p):
            adb('push', p, '/tmp/')
            sh('chmod 777 /tmp/%s' % tool)
    print('[2] busybox + touch -> /tmp/')

    pid = (sh('/tmp/busybox pidof zkgui').stdout or '').strip().split('\n')[0]
    if pid.isdigit():
        _restart_app(pid)
        print('[3] restart zkgui %s' % pid)
    time.sleep(6)
    out = sh('/tmp/busybox ps -o pid,args | /tmp/busybox grep -v grep | /tmp/busybox grep "/bin/zkgui"')
    print('[4] zkgui = %s' % (out.stdout or '').strip()[:60])
    print((sh('/tmp/busybox ls -l /tmp/lib /tmp/ui').stdout or '')[:400])


main()
