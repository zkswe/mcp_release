---
title: 内存信息
---

可通过终端命令和代码的方式查看系统内存的使用情况。

## 终端命令

```bash
# Z6、Z6s、H500s平台
adb shell cat /proc/meminfo
adb shell cat /proc/cpuinfo
adb shell busybox top

# 其他平台
adb shell cat /proc/meminfo
adb shell cat /proc/cpuinfo
adb shell busybox top
```

## 代码

```c++
#define MAX_LINE_LENGTH 256

typedef struct{
 unsigned long MemTotal;
 unsigned long MemFree;
 unsigned long MemAvailable;
 unsigned long Buffers;
 unsigned long Cached;
 unsigned long SwapCached;
 unsigned long Active;
 unsigned long Inactive;
 unsigned long Active_anon;
 unsigned long Inactive_anon;
 unsigned long Active_file;
 unsigned long Inactive_file;
} MemInfo;

MemInfo Getmeminfo(){
 MemInfo memInfo;
 FILE *file = fopen("/proc/meminfo", "r");
 char line[MAX_LINE_LENGTH];

 while (fgets(line, MAX_LINE_LENGTH, file) != NULL) {
 if (strstr(line, "MemTotal:") != NULL) {
 sscanf(line, "MemTotal: %lu kB", &memInfo.MemTotal);
 } else if (strstr(line, "MemFree:") != NULL) {
 sscanf(line, "MemFree: %lu kB", &memInfo.MemFree);
 } else if (strstr(line, "MemAvailable:") != NULL) {
 sscanf(line, "MemAvailable: %lu kB", &memInfo.MemAvailable);
 }
 }
 fclose(file);
 return memInfo;
}
```
