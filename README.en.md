<div align="center">

# 🦅 FlyThings MCP Open

**Give your AI assistant the complete FlyThings development capability: install in one sentence, build FlyThings OS HMI products in one sentence**

**flythings-mcp | FlyThings MCP | FlyThings OS | FlyThings AI assistant | ZKSWE MCP | FlyThings HMI**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Powered-orange.svg)](https://github.com/jlowin/fastmcp)

</div>

---

## ① One-command install

**Option 1: let your AI install it (recommended)** — just tell your AI:

```
Clone and install the project at https://github.com/KWolve/FlyThingsMCP
```

The AI will clone the repo → install dependencies from `requirements.lock` (a locked, verified
version set) → guide you through configuration → done.

> **GitHub (primary): `https://github.com/KWolve/FlyThingsMCP`**; China mirror: `https://gitee.com/Kwolve/flythingsmcp_release`

> Requires Python 3.10+. On Windows you can also double-click `install.bat` (installs deps, then runs an
> offline self-check), or `setup.bat` for an interactive config generator (same as `python configure.py`).
> Pulling the latest yourself is fine too: `pip install mcp onnxruntime tokenizers Pillow` (unpinned, at your own risk).

**2) Point your AI tool at it (stdio)** — create `.mcp.json` **in your project root** (Trae / Cursor / Kimi all read it):

```json
{
  "mcpServers": {
    "flythings-kb-open": {
      "type": "stdio",
      "command": "python",
      "args": ["C:/your/path/flythings-mcp-open/mcp_server.py"]
    }
  }
}
```

Per-tool locations: Trae → project root `.trae/mcp.json` or `.mcp.json`; Cursor → project root `.cursor/mcp.json`
(or Settings → MCP → Add); Kimi → project root `.mcp.json` or `.kimi/mcp.json`; Claude Desktop → `mcpServers`
in `claude_desktop_config.json`.
> If `python` is not on PATH, use the full path (e.g. `C:/Users/<you>/AppData/Local/Programs/Python/Python313/python.exe`).

**3) Verify** — ask your AI “**What is the MCP version?**”:
it should answer `flythings-kb-open 0.27.197-open` with **42 tools** (plus a `binTools` field: pre-built device-side
tools touch / busybox / ui_test / mt_test / zkshot, under `bin_tools/<platform>/` — **not ops, not counted against the op budget**).

> **Three tool-surface modes (pick one per client — don't configure several at once)**
> | Mode | How to configure | What the client sees |
> |------|------------------|----------------------|
> | `dispatcher` (default) | point at `mcp_server.py` only | only the dispatcher `flythings_kb` (`op="list"` for the catalog) — smallest schema cost |
> | `all` | `FLYTHINGS_MCP_MODE=all` | dispatcher + 43 standalone tools (backwards compatible) |
> | `flat` | point at `mcp_server_flat.py` (or `FLYTHINGS_MCP_MODE=flat`) | 43 standalone tools, no dispatcher (for Trae / Cursor / Claude Desktop needing individual schemas; costs ≈ 10k tokens/session) |
>
> Defaulting to “dispatcher only” instead of “register everything” is the **behavior change** of v0.27.34;
> if that affects you, set `FLYTHINGS_MCP_MODE=all` to restore the old behavior.

---

## ② Features

### 🎨 UI layout (json & ftu)
- **Layouts are authored as `ui/*.json`**; `fui pack` produces the `ui/*.ftu` the device actually loads —
  **ftu is a build artifact: never hand-write or hand-edit it** (see `knowledge/devflow/ftu-json-pipeline.md`)
- HTML prototype → json layout (`flythings_html_to_json`); json → reviewable HTML preview
  (`flythings_ui_preview`; projects with multiple full-screen windows get a page switcher)
- Layout parsing (`flythings_read_json`) and field semantics (`knowledge/uicontrols/`)
- **Visual editing**: drag/resize editor → write changes back to json and pack
  (`flythings_ui_visual(action="editor"|"edit_apply")`)
- **Cross-framework control mapping**: LVGL / Qt / Android / mini-program / emWin / MFC controls →
  equivalent FlyThings controls plus paste-ready json snippets (`flythings_map_control`)
- **Image assets**: AI / emoji / line-art three-tier fallback generation (`flythings_generate_ui_assets`);
  size vs. control-box verification (`flythings_verify_assets`, `ui_tools/check_all.py`)

### 🔍 Preview & pixel acceptance
- Browser preview (with `#window__N` deep links and ghost boxes for hidden windows)
- **On-device screenshots** `flythings_device_screenshot`: PNG/JPG/BMP, scaling to save tokens, automatic
  orientation/crop per project config, and video-layer frame grabs
- **Pixel diff** (`flythings_ui_visual(action="diff")`, ±2 tolerance) → 0-token regression acceptance

### 🏭 Build / deploy / package
- `flythings_build_ui_flow`: json/ftu timestamp check → fui pack → fun install → fun build → **device detection + `fun launch` push-and-run**
  > ⚠️ **It pushes to a device by default** (`with_launch` defaults to True since v0.27.84): after build it probes `adb devices -l` —
  > 0 devices → `needDeviceInput=true` + `installHint` (install the **ADB driver** / enable USB debugging and authorize / use `device='<IP>:5555'`);
  > multiple devices → lists serial+model+platform match, **never guesses**, requires an explicit `device=`;
  > exactly 1 matching device → automatically runs `fun launch -s <serial>`.
  > The response carries `launched`/`pushed`/`device`/`model`/`deviceSync` (device-side ftu/so bytes+md5 vs. local)
  > and `staleOnDevice` (true ⇒ the device is still running an old build).
  > **To compile only, pass `with_launch=False` explicitly.**
- **Bundled PC-side adb**: `tools/adb/adb.exe` (+ `AdbWinApi.dll`/`AdbWinUsbApi.dll`, ≈6.1 MB) — no Android SDK needed;
  everything goes through one resolver, `adb_tools.resolve_adb()` (env `ADB`/`FLYTHINGS_ADB` → bundled → PATH);
  device-model→platform table in `device_models.json` (debug: `python adb_tools.py`)
- **Automatic font check + Chinese font delivery** (done **by default** in `flythings_build_ui_flow`): with a device it
  inspects device fonts (`/etc/font`, `/res/font`, `/system/font`); without one it degrades to a project-side check
  (prefs `font` pointer + usable fonts in `font/`). If Chinese is judged **missing**, the **`common` tier Source Han
  Sans (872 KB)** is delivered into the project's `font/` (**before build**, so this build includes it); the response's
  `fontCheck` reports `missingChinese`/`maxFontBytes`/`advisedTier`/`delivered`/`deviceFonts`.
  **Use `font_tier='full'` for rare characters, `'multi'` for multilingual/CJK-JP-KR**; `font_check='off'` disables it;
  to get conclusions without touching the project use `flythings_check_project_deps` (reports only, with a one-line fix command)
- **Font decision uses a hard cmap criterion** (v0.27.87): the largest device font is pulled back and its cmap read,
  measuring coverage of the **3755 GB2312 level-1 characters** —
  **≥90% `ok` (no delivery) / 50–90% `low` (deliver + report coverage) / <50% `missing` (deliver)**; fields
  `source`/`cmapCoverageGB2312L1`/`checkedFont`; over 12 MB or fontTools unavailable → **falls back to a size criterion**
  (`source="size"`, reason in `warnings`); results cached in `~/.fun/font-probe.json`; after a successful `fun launch`
  with a recent delivery, `fontCheck.deviceAfterDeploy` reports device-side font status and consistency
  (**persisting the font requires flashing**, so it is not pulled in vain)
- `flythings_pack_upgrade`: firmware upgrade image `update.img` (TF card / ADB setprop / zkautoupgrade / HTTP OTA)
- **Boot logo replacement**: `boot_logo.JPG` → **MISC partition** (same upgrade mechanism/trigger as `update.img`;
  size must fit the MISC partition — 512 KB measured on this Z21 board, check `cat /proc/mtd` first) →
  `python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG` (generate + size gate) /
  `python tools/set_boot_logo.py --image boot_logo.JPG --device <serial|IP:5555>` (**dry-run by default**, `--yes` to actually trigger);
  details in `knowledge/devflow/upgrade-pack-image.md` §3
- `flythings_create_project` / `flythings_create_bin_project`: create projects from built-in templates
  (F133/F135/Z21/Z20/T113/V85X/Z235X)
  - **ftu can now be unpacked back to json** (v0.27.91): the bundled `toolchain/fui.exe` supports `unpack`, and
    `flythings_fui_unpack` was added (**overwrites the same-named json by default**, ftu is the source of truth;
    pass `overwrite=false` to keep the old json). Passing a `.ftu` to `read_json` no longer fails with
    “encrypted, cannot parse” — it unpacks first.
  - **V85x chip names work as platform inputs** (v0.27.87): `V851 / V851S / V851S3 / V853 / V853S / V553 / V552`
    (any casing) all resolve to **V85X**, with package keys **`v85x` (SPINOR) / `v85xemmc` (EMMC)** —
    **chip names are not package keys** (querying packages with `v851s` returns nothing)
- `flythings_attach_cli_tools`: copies `fui.exe`/`fun.exe` into the project so customers can build and deploy without an IDE
- `flythings_validate_project`: full project convention check (dependencies / framework rules / timestamp guards)
- **Toolchain install (Z235X)**: place the `z235x` toolchain under **`<fun install dir>/toolchains/z235x/`**
  (directory name = lowercase platform key); toolchains are **not distributed** with this package — if it is missing,
  `fun build -p Z235X` fails with `platform toolchain url must not be empty`.

### 🧪 Whole-device self-check & bug reports
- **Device snapshot** `flythings_selfcheck`: nine areas (device info / app status / display / storage / network /
  Bluetooth / input / peripherals / time), each returning `{ok, hint, data}` — **“cannot read” is itself a result**
  (`ok=false` plus a hint explaining what is needed and where to look), never silently swallowed; collection tolerates
  missing device tools (prefers the bundled `bin_tools/<platform>/busybox`, otherwise pure adb shell + getprop/cat);
  `diff_against=<previous.json>` compares area by area, `out=<json>` persists a reusable baseline.
- **Bug report** `flythings_bugreport`: turns AI-produced defect lists + on-device criteria into submittable markdown
  (matching the 2026-09-27 html2json A1–A8 batch: symptom / reproduction / expected vs. actual / on-device criteria /
  evidence / impact), automatically attaching model·firmware·app status·recent `logcat -d -s zkgui` excerpt;
  **missing evidence files raise EVIDENCE_MISSING** (never skipped silently). Default output:
  `<project or package>/temp/bugreports/<yyyymmdd-HHMM>-<slug>.md`.

### 📦 Dependency packages & Manifest
- Package search / versions / header-level APIs (`package_search` / `query_package` / `get_package_api`)
- Manifest generation (`flythings_manifest`, dry-run recommendation by default) → `add_package` →
  recursive `resolve_dependencies` → include reconciliation `check_project_deps`

### 🧠 Knowledge base & hardware
- **Fully offline retrieval** (local bge-small-zh vectors + BM25, two-path RRF, responses carry `quality`/`source`,
  automatic degradation if the model is unavailable) — no API key required
- Hardware model catalog (`flythings_hardware_info`): resolution/orientation, key values, interface specs;
  for unknown models it only offers candidates, never invents specs
- Version / tool-count queries (`flythings_get_version`)

### 🌐 i18n & automated testing
- Multilingual: `scan` / `add_language` / `export` / `import` / `refactor` / `to_json`
- Testing: `flythings_gen_ui_test` (traverse / monkey / custom, on-device touch injection)

### 🧩 Reusable components (`components/`, shipped with this MCP)
- `ble/` (BLE facade `zk::ble`), `fonts/` (three tiers of Source Han Sans + device font self-check),
  `icons/` (single-archive Tabler icon set + on-demand monochrome PNG generation)
- `imagecache/` (decoded-bitmap cache `zk::ImageCache` for list covers — fixes repeated decoding on listview
  refresh/return: **315 ms → 1 ms** measured; see `knowledge/uicontrols/listview-image-cache.md`)
- `ui_v1/`: capabilities the platform lacks, packaged as custom control packages (e.g. `Chart/`, `Calendar/`)
  with examples and on-device evidence

### 🔌 Native MCP primitives
- resources: `flythings://catalog/knowledge`, `flythings://knowledge/<category>/<file>.md`, `flythings://tools`, `flythings://version`
- prompts: `flythings-new-project` / `ui-from-prototype` / `ui-verify` / `deploy-debug` / `package-deps`

---

Current version `0.27.197-open` (42 tools); tool inventory / platform matrix / knowledge snapshot live in
`tools_manifest.json`; the self-check gate is `scripts/check_consistency.py --with-tests`.

Apache License 2.0 · FlyThings Team · Shenzhen ZKSWE Technology Co., Ltd. · [developer.flythings.cn](https://developer.flythings.cn/)
