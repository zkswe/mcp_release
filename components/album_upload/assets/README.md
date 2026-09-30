# assets —— 相册传图的二维码素材与三态口径

> 本目录只有一件事：**二维码怎么出**。传图本体在 `../README.md` 指向的 `components/mp_transfer/`。

## 1. 素材清单

| 文件 | 尺寸 | 说明 |
|---|---|---|
| `album_qr_mp128.png` | **128×128** | 我们的微信小程序码素材（纯黑白二值，1287 B，md5 `5AF8B65E6CBE92A6FAD6D3158B4D144E`）。**尺寸严格 == 控件盒**（原工程 qrcode 控件盒 128×128，外面 160×160 白卡由布局给静区，padding 10）。 |

来源：微信侧给的小程序码原图 → `../scripts/make_qr_asset.py`（裁切=QR 四边形、BOX 缩到 128、二值化、验扫）。
原图**不随本仓分发**（现场找微信侧要）；脚本重跑（同一原图）逐字节一致。

## 2. 三态口径（面板上到底显示什么）

> 一句话：**微信原生小程序码只能远端下载当图片显示**（控件编不出那个带 logo 的码），
> 能"现场生成"的只有「扫普通链接二维码打开小程序」这种**链接码**。所以三态按优先级回落。

| 优先级 | 态 | 判定 | 显示方式 | 内容来源 |
|---|---|---|---|---|
| ① | **远端小程序码图** | 配了 `qr_image_url`（远端码图 URL）**且**本地已下载成功（文件非空） | 图片层（json 里是 `textview` + `backgroundPic`）`setBackgroundPic(本地路径)`；隐藏 qrcode 控件 | 配置项（部署方给） |
| ② | **控件现场生成** | 没配远端图 / 远端图下载失败 **且** `qr_url` 非空 | `ZKQRCode::loadQRCode(qr_url)`（**只在内容变化时重算**） | 配置项；默认值 = 从素材 `album_qr_mp128.png` 解出的「扫普通链接二维码打开小程序」链接 |
| ③ | **本机上传地址兜底** | `qr_url` 被部署方清空 | 同 ②（控件现场生成） | 运行时拼 `http://<面板IP>:9000/upload`（联调保底，不是给终端用户的入口） |

**为什么 ② 比直接铺这张 128px 位图锐利**（真机实拍口径，见 `../platforms.md`）：
素材是 37 模块压在 128px 上 → **128/37 = 3.46 px/模块**，模块宽不是整数像素，边缘必然发糊；
控件现场生成按整数像素对齐模块 → 锐利、扫码更稳。所以 ② 的**内容**从素材里"解"出来，
但**上屏**用控件重画（脚本 `--decode-only` 就是干这个的）。

**为什么还需要 ①**：需要「带中心 logo 的官方小程序码」这种品牌观感时，位图是唯一路径 ——
只有微信服务端能生成它，设备端只能下载显示。

## 3. 换个码 / 换尺寸怎么做（一条命令）

```bash
# 从原图解出链接（填到你的配置项，如 prefs 的 sp_qr_url / kQrUrlDefault）——组件里不许写死
py ../scripts/make_qr_asset.py --src mp_qr.png --decode-only

# 出素材：尺寸默认 128（== 控件盒）；控件盒换了就改 --box
py ../scripts/make_qr_asset.py --src mp_qr.png --out album_qr_mp128.png --box 128 --keep ./qr_asset
#   脚本自带 5 条判据（模块像素/模块数合法/纯黑白/素材可解/模拟上屏可解），出 FAIL 就别上屏
```

⚠️ **静区**：二维码四周要有白边（≈4 模块），靠布局给（原工程：160×160 白卡 + 128 码居中 = 16px 白边）。
素材本身**不含**静区；把码贴到深色底上会扫不出来。

⚠️ **配置项，不许写死**：AppID（`sp_mp_appid` 语义）与链接（`sp_qr_url` 语义）一律由部署方在
prefs/配置里给 —— 本组件与素材都**不带**我方 AppID / 链接常量。
（原工程把"从素材解出的默认链接"当 `kQrUrlDefault` 写在**它自己**的 ConfigStore 里，那是工程的配置默认值，
不是组件常量；本组件只认 `Config::qr_url`。）

## 4. 与组件 API 的对应

| 口径 | `zk::album` 里的对应 |
|---|---|
| ① | `QrInfo{mode=QR_REMOTE_IMAGE, image_url, image_path, image_ready=true}` → 业务显示 `image_path` |
| ② | `QrInfo{mode=QR_LOCAL_GENERATED, content=<qr_url>}` → 业务 `loadQRCode(content)` |
| ③ | `QrInfo{mode=QR_LOCAL_UPLOAD_FALLBACK, content=localUploadUrl()}` |
| 远端图下载失败/重进页 | `notifyQrImageDownloaded(false)` / `resetQrCache()`（+ **业务侧**清自己的"已 load 内容"缓存） |

（详见 `../include/zk/zk_album.h` 的 `QrMode` / `QrInfo` 注释。）
