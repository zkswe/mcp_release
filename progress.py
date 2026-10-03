# -*- coding: utf-8 -*-
"""长任务阶段打点（给 MCP progress notification 用）。

为什么需要：构建 / 部署 / 刷机是**分钟级**任务，客户端只能干等；而这些 op 内部其实
已经有命名阶段（`build_ui_flow` 的 steps：device_probe → fui pack → fun install →
fun build → fun launch）。本模块把这些阶段暴露成一个**跨线程可读**的当前值，
分发器在等结果的同时轮询它，转成 `ctx.report_progress(...)` 推给客户端。

线程模型：op 在工作线程里跑（`anyio.to_thread`），事件循环线程读 `current()`。
所以只用一个锁保护的小字典，不做队列 —— 读到的永远是「最新阶段」，丢中间帧无所谓。
"""
import threading
import time

_lock = threading.Lock()
_state = {'stage': '', 'at': 0.0, 'seq': 0, 'startedAt': 0.0}

STAGE_MAX = 60


def begin(label=''):
    """一个长任务开始：清空阶段并记起点（返回起点时间戳）。"""
    now = time.time()
    with _lock:
        _state['stage'] = str(label)[:STAGE_MAX]
        _state['at'] = now
        _state['seq'] = 0
        _state['startedAt'] = now
    return now


def stage(name):
    """打一个阶段（幂等、无异常：传空则忽略）。"""
    if not name:
        return
    with _lock:
        _state['stage'] = str(name)[:STAGE_MAX]
        _state['at'] = time.time()
        _state['seq'] += 1


def current():
    """当前快照 → {'stage','age','elapsed','seq','running'}（无副作用，随时可读）。"""
    with _lock:
        now = time.time()
        started = _state['startedAt'] or now
        return {'stage': _state['stage'], 'age': round(now - (_state['at'] or now), 1),
                'elapsed': round(now - started, 1), 'seq': _state['seq'],
                'running': bool(_state['startedAt'])}


def end():
    """任务结束：清掉运行标记（阶段名留着，便于事后读）。"""
    with _lock:
        _state['startedAt'] = 0.0


class StageList(list):
    """list 子类：`append` 时顺带打阶段。

    给 `build_ui_flow` 那种「内部已经有 20 处 `steps.append({'step': 'fui pack', ...})`」
    的函数用 —— 一处替换就把所有既有阶段接上进度上报，不必改 20 个调用点。
    """

    def append(self, item):
        list.append(self, item)
        if isinstance(item, dict):
            name = item.get('step') or item.get('name') or ''
            if item.get('success') is False:
                name = '%s（失败）' % name
            stage(name)
