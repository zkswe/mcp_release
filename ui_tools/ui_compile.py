# -*- coding: utf-8 -*-
"""发布版薄壳 —— 实现体不在本文件。

本模块的函数体由 `bin/zkuitool.exe` 承载（Cython 编译的机器码，随包分发）。
此处只保留**签名、常量与转发**，供 MCP 以 `import ui_compile` 的方式继续使用。
"""
from _zktool import rpc as _rpc_call, cli as _cli_call

MOD = 'ui_compile'

__version__ = "0.1.0"
DELEGATED_GEOM_ASSET = "图片尺寸 vs 控件盒 / AA / 倒角 / 透明底 → 由 ui_tools/check_all.py（委派 tools/qa/*）负责"
DELEGATED = ["图片尺寸 vs 控件盒 / AA / 倒角 / 透明底 → 由 ui_tools/check_all.py（委派 tools/qa/*）负责", "T1.4 接口点（未完成，如实登记）：check_all.py 的 json 侧检查项尚未改为调用ui_compile.compile_json —— 现状是两份实现从同一份注册表（ui_schema.json#controls[].children）派生层级判据（数据单一来源、代码尚未合并）；renderContract 的 pic-scale / progress-clip / thumb-size / alpha-compose / edge-aa / stroke-aa / nine-patch / rounding / family-consistency 归 check_all（几何+资产）"]
RULES = {"PARSE001": ["error", "JSON 语法错 / UTF-8 BOM / 非 UTF-8 编码", "用「UTF-8 无 BOM」保存；先把 json 语法修到能解析（fui/easyui 都按严格 json 解析）"], "PARSE002": ["error", "页面根不是对象", "根必须是对象（{...}），至少含 id / resolution / position / backgroundColor"], "PAGE001": ["error", "控件 key 非法或 <type> 未注册", "键名写成 <type>__<n>（type 取注册表 controls/subStructures 里的名字），如 textview__1"], "SCH001": ["fatal", "子盒对象字段写成了标量", "按 sharedTypes 把它写成对象（缺键用 ui_schema_loader.defaults(type) 补）——写成字符串/数字 = 真机 ftu 加载无声挂死"], "SCH002": ["error", "缺必填键", "用 ui_schema_loader.defaults(type) 补齐必填键全集（值等于默认值也要显式写，防版本漂移）"], "SCH003": ["error", "字段类型不符", "按注册表 controls[].fields[].type 改类型（bool 与 int 不通用；-1/0 也要按整数写）"], "SCH004": ["warn", "注册表外未知键", "先确认拼写；确实是字段就先登记进 ui_tools/ui_schema.json（注册表是唯一真源），再写进 json"], "NAME001": ["error", "caption 不是合法 C 标识符", "caption 只能 [A-Za-z_][A-Za-z0-9_]*（要生成 m<caption>Ptr / ID_MAIN_<caption>）；显示文字写 text，不写 caption"], "NAME002": ["error", "caption 同页重复", "同一页 caption 必须唯一（否则指针宏/ID 撞名）；改其中一个的名字"], "ID001": ["error", "id 同页重复或缺失", "同页 id 唯一（按类型分区取号，见 ID002）；注册表 required 的 id 必写"], "ID002": ["warn", "id 不在建议分区段", "按 html2json.ID_BASE 给该类型的分区段取号（仅提示，不影响加载；段宽 = 段基准的最小间隔）"], "TREE001": ["error", "叶子控件装了子控件", "叶子（controls[].children 未声明）不许有子控件键；子控件只能挂容器 —— window 万能容器，pagewindow/scrollwindow 只装 window，listview/slidewindow/radiogroup/diagram 的内容走结构键"], "TREE002": ["error", "结构容器的子内容平铺成子控件键", "结构容器（listview→item / slidewindow→items / radiogroup→radiobuttons / diagram→infos）子内容只能放结构键内，不能平铺 <type>__<n> 控件键（json-layer-rules 第 3 条：结构容器不平铺）"], "TREE003": ["error", "容器只装某类子控件，却装了别的", "pagewindow/scrollwindow 只装 window（内容必须进内层 window）；装别的控件 = 那部分不显示（json-layer-rules 第 4 条）"], "TREE004": ["error", "数组子结构键出现在错的容器里", "数组子结构归属固定：items→slidewindow / infos→diagram / radiobuttons→radiogroup / subItem→listview（json-layer-rules 第 2 条）；放错容器 = 不生效"], "ROOT001": ["error", "根页缺 backgroundColor", "根必须写 backgroundColor（renderContract no-root-bg：引擎靠它擦屏，缺了真机残留上一帧/屏保）"], "CHAR001": ["error", "文本含裁剪字库外的字符", "换 ASCII 或字库内字符（字符集与 check_all.BLACKLIST 同源；emoji/特殊符号真机不显示）"], "ASSET001": ["error", "图片引用指向的文件不存在", "把图放到 <工程根>/resources/<引用路径>，引用写相对 resources 的路径（如 images/x.png）；缺图 = 控件不可见"], "ASSET002": ["error", "图片路径形态非法", "去掉绝对路径 / resources/ 前缀 / 反斜杠，写成相对 resources 的 images/x.png"], "GEOM001": ["error", "position 缺键或非整数", "position 必须 {left,top,width,height} 四个整数（相对父容器；负值合法）"], "RES001": ["error", "页面 resolution 与 --res 声明不符", "确认这页是不是给这块屏的：改 resolution 或换 --res（给错屏的页上机必返工）"], "SCAN001": ["error", "目标下没有可编译的页面 json", "确认路径：工程根要含 ui/*.json（或 ui/<分辨率>/*.json）；也可以直接指向具体 json（0 页 = 什么都没校验，不是通过）"]}

def compile_json(target, res=None, project_root=None, strict=False, rules=None, max_diag=None):
    return _rpc_call(MOD, 'compile_json', target, res, project_root, strict, rules, max_diag)

def compile_project(project_root, res=None, strict=False, rules=None, max_diag=None):
    return _rpc_call(MOD, 'compile_project', project_root, res, strict, rules, max_diag)


if __name__ == '__main__':
    raise SystemExit(_cli_call(MOD))
