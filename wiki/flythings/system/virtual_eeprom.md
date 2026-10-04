---
title: 模拟EEPROM功能
---

通过软件实现模拟EEPROM存储功能。将以下代码完整拷贝到添加的头文件中，实现EEPROM的模拟功能：

```c++
#ifndef JNI_VIREEPROM_H_
#define JNI_VIREEPROM_H_

#include <stdio.h>
#include <string.h>
#include <unistd.h>
/**
 * 模拟EEPROM的存储大小，字节为单位,建议不宜过大
 */
#define EEPROM_SIZE 1024
/**
 * 实际保存为文件 /data/eeprom.eep
 */
#define EEPROM_FILE "/data/eeprom.eep"

class VirEEPROM {

public:
 VirEEPROM() {
 memset(buff_, 0, sizeof(buff_));
 file_ = fopen(EEPROM_FILE, "rb+");
 if (file_) {
 fread(buff_, 1, EEPROM_SIZE, file_);
 fseek(file_, 0, SEEK_END);
 int f_size = ftell(file_);
 if (f_size != sizeof(buff_)) {
 ftruncate(fileno(file_), sizeof(buff_));
 fseek(file_, 0, SEEK_SET);
 fwrite(buff_, 1, sizeof(buff_), file_);
 fflush(file_);
 sync();
 }
 } else {
 file_ = fopen(EEPROM_FILE, "wb+");
 ftruncate(fileno(file_), sizeof(buff_));
 }
 }
 virtual ~VirEEPROM() {
 if (file_) {
 fflush(file_);
 fclose(file_);
 sync();
 }
 }
 int Write(int addr, const void* value, int size) {
 if (file_ == NULL) return -1;
 if ((addr >= EEPROM_SIZE) || ((addr + size) > EEPROM_SIZE)) return -2;
 memcpy(buff_ + addr, value, size);
 if (0 != fseek(file_, addr, SEEK_SET)) return -3;
 int n = fwrite((char*)value, 1, size, file_);
 fflush(file_);
 sync();
 return n;
 }
 int Read(int addr, void* value, int size) {
 if (file_ == NULL) return -1;
 if ((addr >= EEPROM_SIZE) || ((addr + size) > EEPROM_SIZE)) return -2;
 memcpy(value, buff_ + addr, size);
 return size;
 }
 int Erase() {
 if (file_ == NULL) return -1;
 if (0 != fseek(file_, 0, SEEK_SET)) return -2;
 memset(buff_, 0, sizeof(buff_));
 if (sizeof(buff_) != fwrite(buff_, 1, sizeof(buff_), file_)) return -3;
 fflush(file_);
 sync();
 return 0;
 }

 static VirEEPROM* getInstance() {
 static VirEEPROM singleton;
 return &singleton;
 }
private:
 unsigned char buff_[EEPROM_SIZE];
 FILE* file_;
};

#define VIREEPROM VirEEPROM::getInstance()

#endif /* JNI_VIREEPROM_H_ */
```
