/*
 * h264player-v85x —— V85X 硬件 H264 播放验证工具（bin 工程，无 UI）
 *
 * 用法：
 *   h264play <file.h264> <srcW> <srcH> [rot=0|90|180|270] [scale=1|2|4] [seconds=10]
 *   h264play                                     # 打印用法
 *
 * 作用：按 Annex-B 的 access unit 切分喂给硬件解码器，打印「解码回调」与内存占用
 *       —— 排查"解码到底有没有出画 / 是不是内存不够"的硬证据。
 *
 * 为什么用 dlopen 而不是直接链：
 *   V85X 上把官方包 awh264player 的 libawh264player.so 直接放到链接行会失败
 *   （bin 工程带 -Wl,-z,defs；该 .so 内部依赖全志侧 CreateVideoDecoder / hw_display_init /
 *    hwd_layer_* 等符号，补 aw-mpp 又会拉进 alsa 的 snd_*，而 v85x 没有 alsa 包）。
 *   厂商参考工程也是 dlopen 形态 ⇒ 本 demo 照此实现，兼容"库在 /tmp 调试推送"与"固化后 /res/lib"两种情况。
 *
 * 关键点（都在代码里留了注释，别回退）：
 *   ① ZKMEDIA_H264_VBVSIZE 必须在 dlopen **之前** setenv —— 不设则 720p 起播「进程静默消失」；
 *   ② 缩放只能用 h264_player_init_ex（三参的 h264_player_init 没有 flag 参数）；
 *   ③ 起播前后打印 MemAvailable —— < 3MB 必挂（被 OOM 杀过的进程内存不会自己回来，要重启板子）；
 *   ④ 判断"有没有真出画"只看解码回调，不看 h264_player_get_picture_count（那不是队列长度）。
 *
 * 依赖：把官方包 awh264player@1.0.0 的 include/h264_player.h 放进 src/dependencies/include/，
 *      把 lib/libawh264player.so 放进 src/dependencies/lib-no-link/（只打包、不参与链接）；
 *      调试期还要 adb push 到 /tmp（fun launch 不推 lib-no-link）。
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <string>
#include <unistd.h>
#include <dlfcn.h>

#include "h264_player.h"

namespace {

// ---- 用 dlopen 拿到的真实现（h264_player_*，符号名与官方包头文件一致）----
void *g_lib = NULL;
int (*p_init_ex)(int, int, enum disp_rot_e, int) = NULL;
void (*p_deinit)() = NULL;
void (*p_set_decode_cb)(h264_decode_frame_cb) = NULL;
void (*p_show)() = NULL;
void (*p_hide)() = NULL;
void (*p_set_pos)(int, int, int, int) = NULL;
void (*p_put_frame)(uint8_t *, uint32_t) = NULL;

int g_decodedFrames = 0;   // 解码回调次数 = "真的出画了"的唯一证据
int g_fedFrames = 0;
bool g_printedFirst = false;

int memAvailableKb() {
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return -1;
    char line[256];
    int kb = -1;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "MemAvailable:", 13) == 0) { kb = atoi(line + 13); break; }
    }
    fclose(f);
    return kb;
}

void onFrame(h264_decode_frame_t *frame) {
    if (!frame) return;
    ++g_decodedFrames;
    if (!g_printedFirst || (g_decodedFrames % 60) == 0) {
        // width/height 是解码缓冲尺寸（可能带 16 对齐）；有效画面看 crop
        printf("[cb] 解码回调 #%d —— buf=%dx%d crop(%d,%d,%d,%d) fmt=%d data0=%p\n",
               g_decodedFrames, frame->width, frame->height,
               frame->left, frame->top, frame->right, frame->bottom,
               frame->fmt, static_cast<void *>(frame->data0));
        fflush(stdout);
        g_printedFirst = true;
    }
}

// 逐个候选路径 dlopen（调试期在 /tmp，固化后在 /res/lib；设备 ld 路径已含这两处）
bool loadLibrary(std::string *usedPath) {
    const char *cands[] = {
        "libawh264player.so",                  // 交给 ld 搜索路径（/data:/tmp:/res/lib:/lib:...）
        "/res/lib/libawh264player.so",
        "/tmp/libawh264player.so",
        "/tmp/libawh264player_dev.so",         // 不同名库可并存（调试期用）
        "/data/libawh264player.so",
        NULL
    };
    for (int i = 0; cands[i]; ++i) {
        g_lib = dlopen(cands[i], RTLD_NOW);
        if (g_lib) { *usedPath = cands[i]; return true; }
        printf("[dl] 打开 %-28s 失败: %s\n", cands[i], dlerror());
    }
    return false;
}

// Annex-B：取起始码后第一个 NAL 的 type
int nalType(const uint8_t *p, size_t n) {
    size_t i = 0;
    while (i + 3 <= n) {
        if (p[i] == 0 && p[i + 1] == 0 && p[i + 2] == 1) return p[i + 3] & 0x1F;
        if (i + 4 <= n && p[i] == 0 && p[i + 1] == 0 && p[i + 2] == 0 && p[i + 3] == 1)
            return p[i + 4] & 0x1F;
        ++i;
    }
    return -1;
}

// 切 access unit：优先按 AUD(9)；没有 AUD 就退化成"每个 IDR(5) 开新 AU"
std::vector<std::pair<size_t, size_t> > splitAccessUnits(const std::vector<uint8_t> &es) {
    std::vector<size_t> starts;
    bool haveAud = false;
    size_t i = 0;
    while (i + 3 <= es.size()) {
        size_t scLen = 0;
        if (es[i] == 0 && es[i + 1] == 0 && es[i + 2] == 1) scLen = 3;
        else if (es[i] == 0 && es[i + 1] == 0 && es[i + 2] == 0 && i + 4 <= es.size() && es[i + 3] == 1) scLen = 4;
        if (scLen) {
            if (i + scLen < es.size()) {
                if ((es[i + scLen] & 0x1F) == 9) haveAud = true;
                starts.push_back(i);
                i += scLen;
                continue;
            }
            break;
        }
        ++i;
    }
    std::vector<std::pair<size_t, size_t> > aus;
    if (starts.empty()) return aus;
    if (haveAud) {
        for (size_t k = 0; k + 1 < starts.size(); ++k) {
            size_t end = (k + 1 < starts.size()) ? starts[k + 1] : es.size();
            if (nalType(&es[starts[k]], end - starts[k]) == 9 &&
                nalType(&es[starts[k + 1]], ((k + 2 < starts.size()) ? starts[k + 2] : es.size()) - starts[k + 1]) != 9) {
                // AUD 之后到下个 AUD 之前 = 一个 AU；非 AUD 的下一段也一并并入
                size_t auEnd = (k + 2 < starts.size()) ? starts[k + 2] : es.size();
                // 合并紧随其后的非 AUD 段
                size_t k2 = k + 1;
                while (k2 + 1 < starts.size() &&
                       nalType(&es[starts[k2 + 1]], ((k2 + 2 < starts.size()) ? starts[k2 + 2] : es.size()) - starts[k2 + 1]) != 9) {
                    break;
                }
                aus.push_back(std::make_pair(starts[k + 1], auEnd));
            }
        }
        if (!aus.empty()) return aus;
    }
    // 退化：每遇到 IDR 开一个新 AU
    size_t cur = 0;
    for (size_t k = 0; k < starts.size(); ++k) {
        size_t end = (k + 1 < starts.size()) ? starts[k + 1] : es.size();
        if (nalType(&es[starts[k]], end - starts[k]) == 5 && k > 0) {
            aus.push_back(std::make_pair(cur, starts[k]));
            cur = starts[k];
        }
    }
    aus.push_back(std::make_pair(cur, es.size()));
    return aus;
}

bool readWholeFile(const char *path, std::vector<uint8_t> &out) {
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (n <= 0) { fclose(f); return false; }
    out.resize(static_cast<size_t>(n));
    size_t rd = fread(&out[0], 1, out.size(), f);
    fclose(f);
    return rd == out.size();
}

enum disp_rot_e parseRot(int deg) {
    switch (deg) {
        case 90:  return E_DISP_ROT_90;
        case 180: return E_DISP_ROT_180;
        case 270: return E_DISP_ROT_270;
        default:  return E_DISP_ROT_0;
    }
}

#define BIND(name) do { \
        *(void **)(&p_##name) = dlsym(g_lib, "h264_player_" #name); \
        if (!p_##name) { printf("[err] dlsym h264_player_" #name " 失败: %s\n", dlerror()); return 4; } \
    } while (0)

void usage(const char *argv0) {
    printf("用法: %s <file.h264> <srcW> <srcH> [rot=0|90|180|270] [scale=1|2|4] [seconds=10]\n", argv0);
    printf("例:   %s /tmp/test_720p.h264 1280 720 0 2 15\n", argv0);
    printf("说明: srcW/srcH 是**源**分辨率（不是显示区）；scale=2 会用 SCALE_DOWN_2 缩放解码。\n");
}

}  // namespace

int main(int argc, char **argv) {
    if (argc < 4) { usage(argv[0]); return 1; }

    const char *path = argv[1];
    const int srcW = atoi(argv[2]);
    const int srcH = atoi(argv[3]);
    const int rotDeg = (argc > 4) ? atoi(argv[4]) : 0;
    const int scale = (argc > 5) ? atoi(argv[5]) : 1;
    const int seconds = (argc > 6) ? atoi(argv[6]) : 10;

    // ① 环境变量必须在 dlopen 之前设好（库在加载时读它）
    //    第三个参数 0 = 外部已设的不覆盖（现场调大：export ZKMEDIA_H264_VBVSIZE=2097152）
    setenv("ZKMEDIA_H264_VBVSIZE", "1048576", 0);

    std::string used;
    if (!loadLibrary(&used)) {
        printf("[err] 找不到 libawh264player.so：调试期请 adb push 到 /tmp（fun launch 不推 lib-no-link）\n");
        return 2;
    }
    printf("[dl] 已加载 %s\n", used.c_str());

    BIND(init_ex); BIND(deinit); BIND(set_decode_cb); BIND(show); BIND(hide);
    BIND(set_pos); BIND(put_frame);

    std::vector<uint8_t> es;
    if (!readWholeFile(path, es)) {
        printf("[err] 读文件失败: %s（确认文件在设备上、且是 Annex-B ES）\n", path);
        return 3;
    }
    std::vector<std::pair<size_t, size_t> > aus = splitAccessUnits(es);
    printf("[cfg] %s (%zu 字节) / 源 %dx%d / rot=%d / 1/%d 缩放 / AU 数 %zu\n",
           path, es.size(), srcW, srcH, rotDeg, scale, aus.size());
    printf("[mem] 起播前 MemAvailable = %d kB\n", memAvailableKb());

    int flag = E_H264_PLAYER_FLAG_STREAM_EOF;
    if (scale == 2) flag |= E_H264_PLAYER_FLAG_SCALE_DOWN_2;
    if (scale == 4) flag |= E_H264_PLAYER_FLAG_SCALE_DOWN_4;

    // ② 缩放必须走 init_ex（三参 h264_player_init 没有 flag 参数）
    const int r = p_init_ex(srcW, srcH, parseRot(rotDeg), flag);
    printf("[cfg] h264_player_init_ex(%d,%d,rot=%d,flag=0x%x) -> %d\n", srcW, srcH, rotDeg, flag, r);
    if (r != 0) {
        printf("[err] init 失败：先查 MemAvailable>=3MB，再查 VBVSIZE（改完要重启应用）\n");
        return 5;
    }

    p_set_decode_cb(onFrame);
    p_set_pos(0, 0, 480, 270);   // 显示区（屏幕坐标）；按实际屏幕改
    p_show();
    printf("[mem] init 后 MemAvailable = %d kB\n", memAvailableKb());

    // 约 30fps 节流喂帧（真实流请用媒体时间做背压，别用 get_picture_count）
    const useconds_t frameUs = 33000;
    for (size_t i = 0; i < aus.size(); ++i) {
        p_put_frame(const_cast<uint8_t *>(&es[aus[i].first]),
                    static_cast<uint32_t>(aus[i].second - aus[i].first));
        ++g_fedFrames;
        if ((g_fedFrames % 30) == 0) {
            printf("[feed] 已喂 %d 包 / 解码出帧 %d / MemAvailable=%d kB\n",
                   g_fedFrames, g_decodedFrames, memAvailableKb());
            fflush(stdout);
        }
        usleep(frameUs);
        if (seconds > 0 && (long)g_fedFrames * (long)(frameUs / 1000) > (long)seconds * 1000) {
            printf("[feed] 到时（%d 秒），停止喂帧\n", seconds);
            break;
        }
    }

    printf("[stat] 喂 %d 包 / 解码回调 %d 次 %s\n", g_fedFrames, g_decodedFrames,
           (g_decodedFrames > 0) ? "(硬件解码出画 ✅)" : "(一帧没出 ❌ 查 SPS/PPS/IDR 与内存)");
    p_hide();
    p_deinit();
    if (g_lib) dlclose(g_lib);
    printf("[mem] deinit 后 MemAvailable = %d kB\n", memAvailableKb());
    return 0;
}
