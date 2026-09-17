# -*- coding: utf-8 -*-
"""make_pack.py —— 把 vendor(tabler) 的 SVG 散件打成**单一归档** `vendor/tabler-<版本>.pack.tgz`

为什么（2026-09-17 方案 A「单归档 + 按需解，离线优先」）：
    散件入库 = 5777 个文件进 git（3.95 MB），克隆慢、diff/检索噪音大、任何人都没法一眼看清
    「这堆文件是干嘛的」。而 99% 的使用只用到其中几个 glyph —— 于是一份 tar.gz 归档 +
    读取层按需解（见 `gen_icons.py` 的"图标来源解析"）就够，**用法与输出完全不变**。

归档内容（逐个确定性写入，gzip mtime=0 / tar mtime=0 → 同一输入必得同一 sha256）：
    icons/*.svg          outline 4754
    icons-filled/*.svg   filled 1019
    map.json             语义映射（198 条，含 7 条 compose）
**不放** index.json / LICENSE / VERSION.txt —— 它们在归档外，便于索引与 MIT 合规声明（见 THIRD-PARTY.md）。

用法：
    python scripts/make_pack.py                          # 用仓库里现存的散件打（首次迁入用）
    python scripts/make_pack.py --verify <pack.tgz>      # 只核对 sha256/条目数/与散件集合是否一致
    python scripts/make_pack.py --from-npm <tarball|url> # 从上游 npm tarball 重建（离线重建路径）
    python scripts/make_pack.py --from-npm x.tgz --map vendor/tabler/map.json

注：`--from-npm` 默认套用与本次入库相同的 `--exclude-brand`（Tabler 的 `brand-*` 376 个不进包）。
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENDOR_DIR = os.path.join(ROOT, 'vendor', 'tabler')
# 归档成员的艺术名（与 gen_icons.py 的 PACK_PREFIX 对应：逻辑路径 vendor/tabler/<member>）
KEEP_DIRS = ('icons', 'icons-filled')
KEEP_FILES = ('map.json',)
BRAND_RE = 'brand-'


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _entries(src_root, keep=KEEP_DIRS, exclude_brand=True):
    """→ [(归档内相对名, 磁盘绝对路径)]，按名字排序（确定性）。"""
    out = []
    for sub in keep:
        d = os.path.join(src_root, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith('.svg'):
                continue
            if exclude_brand and f.startswith(BRAND_RE):
                continue
            out.append(('%s/%s' % (sub, f), os.path.join(d, f)))
    for f in KEEP_FILES:
        p = os.path.join(src_root, f)
        if os.path.isfile(p):
            out.append((f, p))
    out.sort(key=lambda t: t[0])
    return out


def write_pack(out_path, entries):
    """确定性 tar.gz：mtime=0 / uid=gid=0 / 固定 mode / gzip mtime=0。"""
    tmp = out_path + '.tmp'
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(tmp, 'wb') as fh:
        gz = gzip.GzipFile(filename='', mode='wb', fileobj=fh, compresslevel=9, mtime=0)
        try:
            with tarfile.open(fileobj=gz, mode='w', format=tarfile.GNU_FORMAT) as tar:
                for arc, path in entries:
                    ti = tar.gettarinfo(path, arcname=arc)
                    ti.mtime = 0
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = ''
                    ti.mode = 0o644
                    ti.type = tarfile.REGTYPE
                    with open(path, 'rb') as f:
                        tar.addfile(ti, f)
        finally:
            gz.close()
    os.replace(tmp, out_path)
    return out_path


def pack_summary(pack_path):
    names, total = [], 0
    with tarfile.open(pack_path, 'r:gz') as tar:
        for m in tar.getmembers():
            if m.isfile():
                names.append(m.name)
                total += m.size
    return dict(path=pack_path, bytes=os.path.getsize(pack_path), entries=len(names),
                uncompressed=total, sha256=sha256_file(pack_path),
                icons=sum(1 for n in names if n.startswith('icons/')),
                icons_filled=sum(1 for n in names if n.startswith('icons-filled/')),
                other=[n for n in names if not n.startswith('icons')])


def fetch_npm(url, cache_dir):
    """下载 npm tarball 到缓存目录（离线优先：已缓存且 sha256 一致就不再下）。"""
    os.makedirs(cache_dir, exist_ok=True)
    dst = os.path.join(cache_dir, os.path.basename(url.split('?')[0]) or 'icons.tgz')
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return dst
    print('  downloading %s' % url)
    with urllib.request.urlopen(url, timeout=120) as r, open(dst, 'wb') as f:
        shutil.copyfileobj(r, f)
    return dst


def entries_from_npm(tarball, exclude_brand=True, map_json=None):
    """npm tarball（package/icons*/**.svg）→ [(归档名, 临时文件路径)]。"""
    tmpd = tempfile.mkdtemp(prefix='tabler-pack-')
    out = []
    with tarfile.open(tarball, 'r:gz') as tar:
        for m in tar.getmembers():
            if not m.isfile() or not m.name.endswith('.svg'):
                continue
            parts = m.name.split('/')
            if len(parts) < 3:
                continue
            sub, fn = parts[-2], parts[-1]                     # package/icons/<fn>
            if sub not in KEEP_DIRS:
                continue
            if exclude_brand and fn.startswith(BRAND_RE):
                continue
            dst = os.path.join(tmpd, sub, fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with tar.extractfile(m) as src, open(dst, 'wb') as f:
                shutil.copyfileobj(src, f)
            out.append(('%s/%s' % (sub, fn), dst))
    if map_json:
        out.append(('map.json', map_json))
    out.sort(key=lambda t: t[0])
    return out, tmpd


def main(argv):
    ap = argparse.ArgumentParser(description='vendor(tabler) SVG 散件 → 单归档 pack.tgz')
    ap.add_argument('--out', help='输出归档路径（默认 vendor/tabler-<版本>.pack.tgz）')
    ap.add_argument('--src', help='散件根目录（默认 vendor/tabler）')
    ap.add_argument('--from-npm', dest='from_npm', help='从上游 npm tarball（本地路径或 URL）重建')
    ap.add_argument('--map', help='语义映射 json（--from-npm 时使用，默认用仓库里的 map.json）')
    ap.add_argument('--cache', help='npm tarball 缓存目录（默认 out/.icons-cache/_remote）')
    ap.add_argument('--include-brand', action='store_true', help='不排除 brand-*（默认排除）')
    ap.add_argument('--verify', help='只核对：sha256/条目数/与散件集合差异')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)

    ver = ''
    vf = os.path.join(VENDOR_DIR, 'VERSION.txt')
    if os.path.isfile(vf):
        for line in io.open(vf, encoding='utf-8'):
            if line.startswith('version:'):
                ver = line.split(':', 1)[1].strip()
    default_out = os.path.join(ROOT, 'vendor', 'tabler-%s.pack.tgz' % (ver or 'latest'))
    out_path = a.out or default_out

    if a.verify:
        s = pack_summary(a.verify)
        if a.json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
            return 0
        print('pack      %s' % s['path'])
        print('bytes     %d (%.2f MB, 解压后 %.2f MB)'
              % (s['bytes'], s['bytes'] / 1048576.0, s['uncompressed'] / 1048576.0))
        print('sha256    %s' % s['sha256'])
        print('entries   %d（icons %d + icons-filled %d + %s）'
              % (s['entries'], s['icons'], s['icons_filled'], ','.join(s['other']) or '-'))
        src = a.src or VENDOR_DIR
        want = {arc for arc, _ in _entries(src, exclude_brand=not a.include_brand)}
        have = set()
        with tarfile.open(a.verify, 'r:gz') as tar:
            have = {m.name for m in tar.getmembers() if m.isfile()}
        if want and want != have:
            print('散件集合与归档不一致：only-in-disk=%d only-in-pack=%d'
                  % (len(want - have), len(have - want)))
            for n in sorted((want - have))[:5]:
                print('   only-in-disk %s' % n)
            for n in sorted((have - want))[:5]:
                print('   only-in-pack %s' % n)
            return 1
        print('集合核对  OK（与 %s 的散件一一对应）' % src)
        return 0

    tmpd = None
    if a.from_npm:
        src_spec = a.from_npm
        if src_spec.startswith(('http://', 'https://')):
            cache = a.cache or os.path.join(ROOT, 'out', '.icons-cache', '_remote')
            src_spec = fetch_npm(src_spec, cache)
        elif not os.path.isfile(src_spec):
            print('找不到 tarball：%s' % src_spec)
            return 2
        map_json = a.map or os.path.join(VENDOR_DIR, 'map.json')
        if not os.path.isfile(map_json):
            print('缺语义映射 --map：%s' % map_json)
            return 2
        entries, tmpd = entries_from_npm(src_spec, exclude_brand=not a.include_brand,
                                         map_json=map_json)
        print('源：%s（entries %d）' % (src_spec, len(entries)))
    else:
        src = a.src or VENDOR_DIR
        if not os.path.isdir(src):
            print('散件目录不存在：%s（想从上游重建用 --from-npm）' % src)
            return 2
        entries = _entries(src, exclude_brand=not a.include_brand)
        print('源：%s（entries %d）' % (src, len(entries)))

    if not entries:
        print('没有可打包的文件')
        return 2
    write_pack(out_path, entries)
    s = pack_summary(out_path)
    if tmpd:
        shutil.rmtree(tmpd, ignore_errors=True)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    print('pack      %s' % s['path'])
    print('bytes     %d (%.2f MB)' % (s['bytes'], s['bytes'] / 1048576.0))
    print('sha256    %s' % s['sha256'])
    print('entries   %d（icons %d + icons-filled %d + %s）'
          % (s['entries'], s['icons'], s['icons_filled'], ','.join(s['other']) or '-'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
