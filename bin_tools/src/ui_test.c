/*
 * ui_test.c — 通用触摸注入/自动化测试工具（跨平台预编译 ELF）
 *
 * 用法:
 *   ui_test <dev> tap x y
 *   ui_test <dev> swipe x1 y1 x2 y2
 *   ui_test <dev> monkey <w> <h> <count>
 *   ui_test <dev> run <script.txt>          # 脚本每行: tap x y / swipe x1 y1 x2 y2 / delay ms
 *   ui_test <dev> record <out.txt>          # 录制触摸事件到文本（可选）
 *
 * 脚本格式（run）:
 *   # 注释
 *   tap 192 207
 *   swipe 100 200 800 600
 *   delay 500
 *
 * 实现基于 event.c 的触摸注入方法：
 *   按下: EV_ABS ABS_X/Y → ABS_PRESSURE → EV_KEY BTN_TOUCH=1 → EV_SYN
 *   移动: EV_ABS ABS_X/Y 逐点 → EV_SYN（中点插值）
 *   抬起: ABS_PRESSURE=0 → BTN_TOUCH=0 → EV_SYN
 * ⚠️ EV_SYN 必须发，否则内核不提交事件。
 */
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <errno.h>
#include <stdint.h>
#include <linux/input.h>
#include <sys/time.h>

static int reportkey(int fd, uint16_t type, uint16_t code, int32_t value) {
    struct input_event event;
    event.type = type; event.code = code; event.value = value;
    gettimeofday(&event.time, 0);
    if (write(fd, &event, sizeof(struct input_event)) < 0) {
        fprintf(stderr, "report key error %s!\n", strerror(errno));
        return -1;
    }
    return 0;
}

/* 按下 */
static int touch_down(int fd, int x, int y) {
    reportkey(fd, EV_ABS, ABS_X, x);
    reportkey(fd, EV_ABS, ABS_Y, y);
    reportkey(fd, EV_ABS, ABS_PRESSURE, 100);
    reportkey(fd, EV_KEY, BTN_TOUCH, 1);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
    return 0;
}

/* 抬起 */
static int touch_up(int fd) {
    reportkey(fd, EV_ABS, ABS_PRESSURE, 0);
    reportkey(fd, EV_KEY, BTN_TOUCH, 0);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
    return 0;
}

/* 移动一步 */
static int touch_move(int fd, int x, int y) {
    reportkey(fd, EV_ABS, ABS_X, x);
    reportkey(fd, EV_ABS, ABS_Y, y);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
    return 0;
}

/* 点击 */
static void tap(int fd, int x, int y) {
    printf("[UITEST] tap (%d,%d)\n", x, y);
    touch_down(fd, x, y);
    usleep(60 * 1000);
    touch_up(fd);
}

/* 滑动（中点插值） */
static void swipe(int fd, int x1, int y1, int x2, int y2) {
    printf("[UITEST] swipe (%d,%d)->(%d,%d)\n", x1, y1, x2, y2);
    touch_down(fd, x1, y1);
    int dx = x2 - x1, dy = y2 - y1;
    int steps = (abs(dx) > abs(dy) ? abs(dx) : abs(dy)) / 8;
    if (steps < 4) steps = 4;
    for (int i = 1; i <= steps; i++) {
        touch_move(fd, x1 + dx * i / steps, y1 + dy * i / steps);
        usleep(8 * 1000);
    }
    usleep(40 * 1000);
    touch_up(fd);
}

/* 长按 */
static void long_press(int fd, int x, int y, int ms) {
    printf("[UITEST] long_press (%d,%d) %dms\n", x, y, ms);
    touch_down(fd, x, y);
    usleep(ms * 1000);
    touch_up(fd);
}

/* Monkey 随机压测 */
static void monkey(int fd, int w, int h, int count) {
    printf("[MONKEY] screen=%dx%d count=%d start\n", w, h, count);
    srand(time(NULL));
    for (int i = 0; i < count; i++) {
        int r = rand() % 100;
        if (r < 65) {
            int x = rand() % w, y = rand() % h;
            printf("[MONKEY] %d/%d tap (%d,%d)\n", i + 1, count, x, y);
            tap(fd, x, y);
        } else {
            int x1 = rand() % w, y1 = rand() % h;
            int x2 = rand() % w, y2 = rand() % h;
            printf("[MONKEY] %d/%d swipe (%d,%d)->(%d,%d)\n", i + 1, count, x1, y1, x2, y2);
            swipe(fd, x1, y1, x2, y2);
        }
        usleep(150 * 1000);
    }
    printf("[MONKEY] done\n");
}

/* 执行脚本文件 */
static int run_script(int fd, const char *path) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        fprintf(stderr, "open script %s failed: %s\n", path, strerror(errno));
        return 1;
    }
    char line[256];
    int n = 0;
    while (fgets(line, sizeof(line), fp)) {
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == '\n' || *p == '\r' || *p == 0) continue;
        char cmd[32];
        int a, b, c, d;
        if (sscanf(p, "%31s %d %d %d %d", cmd, &a, &b, &c, &d) >= 3) {
            n++;
            if (strcmp(cmd, "tap") == 0) {
                tap(fd, a, b);
            } else if (strcmp(cmd, "swipe") == 0) {
                swipe(fd, a, b, c, d);
            } else if (strcmp(cmd, "long") == 0 || strcmp(cmd, "long_press") == 0) {
                long_press(fd, a, b, c);
            } else if (strcmp(cmd, "delay") == 0) {
                printf("[UITEST] delay %dms\n", a);
                usleep(a * 1000);
            }
        } else {
            fprintf(stderr, "skip bad line: %s", p);
        }
        usleep(100 * 1000);  /* 指令间隔 100ms */
    }
    fclose(fp);
    printf("[UITEST] script done (%d steps)\n", n);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr,
            "usage: ui_test <dev> tap x y\n"
            "       ui_test <dev> swipe x1 y1 x2 y2\n"
            "       ui_test <dev> monkey <w> <h> <count>\n"
            "       ui_test <dev> run <script.txt>\n"
            "       ui_test <dev> long x y ms\n");
        return 1;
    }
    const char *dev = argv[1];
    const char *cmd = argv[2];
    int fd = open(dev, O_WRONLY);
    if (fd < 0) {
        fprintf(stderr, "open %s failed: %s\n", dev, strerror(errno));
        return 1;
    }
    int rc = 0;
    if (strcmp(cmd, "tap") == 0 && argc >= 5) {
        tap(fd, atoi(argv[3]), atoi(argv[4]));
    } else if (strcmp(cmd, "swipe") == 0 && argc >= 7) {
        swipe(fd, atoi(argv[3]), atoi(argv[4]), atoi(argv[5]), atoi(argv[6]));
    } else if (strcmp(cmd, "long") == 0 && argc >= 6) {
        long_press(fd, atoi(argv[3]), atoi(argv[4]), atoi(argv[5]));
    } else if (strcmp(cmd, "monkey") == 0 && argc >= 6) {
        monkey(fd, atoi(argv[3]), atoi(argv[4]), atoi(argv[5]));
    } else if (strcmp(cmd, "run") == 0 && argc >= 4) {
        rc = run_script(fd, argv[3]);
    } else {
        fprintf(stderr, "unknown cmd or bad args: %s\n", cmd);
        rc = 1;
    }
    close(fd);
    return rc;
}
