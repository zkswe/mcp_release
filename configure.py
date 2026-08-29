# -*- coding: utf-8 -*-
"""FlyThings MCP 一键配置：自动检测运行方式（exe 优先），生成 AI 工具配置文件。
用法：在任意目录运行  python 本文件路径/configure.py  （或双击 setup.bat）
生成的 .mcp.json 等配置写入当前工作目录（建议在你的项目根目录运行）。
"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))


def detect_command():
    """优先用打包的 exe（免 Python）；否则用 python + mcp_server.py。"""
    exe = os.path.join(BASE, 'dist', 'mcp_server.exe')
    if os.path.isfile(exe):
        return exe, []
    py = sys.executable
    return py, [os.path.join(BASE, 'mcp_server.py')]


def make_cfg(cmd, args):
    cfg = {'type': 'stdio', 'command': cmd}
    if args:
        cfg['args'] = args
    return {'mcpServers': {'flythings-kb': cfg}}


def write(path, cfg):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f'  [OK] 已生成: {path}')
        return True
    except Exception as e:
        print(f'  [!!] 写入失败 {path}: {e}')
        return False


def main():
    cwd = os.getcwd()
    cmd, args = detect_command()
    kind = 'mcp_server.exe（免 Python）' if os.path.basename(cmd).endswith('.exe') else 'python + mcp_server.py'
    print('=' * 56)
    print('  FlyThings MCP 一键配置')
    print('=' * 56)
    print(f'  运行方式: {kind}')
    print(f'  命令: {cmd}')
    if args:
        print(f'  参数: {args}')
    print(f'  配置写入目录: {cwd}')
    print()
    print('  1) 只生成 .mcp.json（通用，Trae/Kimi/Cursor 都识别）')
    print('  2) 生成 .trae/mcp.json（Trae 专用）')
    print('  3) 生成 .cursor/mcp.json（Cursor 专用）')
    print('  4) 生成 .kimi/mcp.json（Kimi 专用）')
    print('  5) 全部生成（推荐）')
    print('  0) 不生成，只打印配置内容')
    choice = input('  请选择 (0-5，回车=5): ').strip() or '5'
    print()
    cfg = make_cfg(cmd, args)
    if choice in ('1', '5'):
        write('.mcp.json', cfg)
    if choice in ('2', '5'):
        os.makedirs('.trae', exist_ok=True)
        write(os.path.join('.trae', 'mcp.json'), cfg)
    if choice in ('3', '5'):
        os.makedirs('.cursor', exist_ok=True)
        write(os.path.join('.cursor', 'mcp.json'), cfg)
    if choice in ('4', '5'):
        os.makedirs('.kimi', exist_ok=True)
        write(os.path.join('.kimi', 'mcp.json'), cfg)
    if choice == '0':
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    print()
    print('  完成！请在 AI 工具中重新打开/刷新项目。')
    print('  验证：问 AI「MCP 版本是多少？」应返回 flythings-kb 0.2.4（22 个工具）。')
    print('=' * 56)
    input('  按回车退出...')


if __name__ == '__main__':
    main()
