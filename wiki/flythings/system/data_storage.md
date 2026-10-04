---
title: 数据存储
---

在某些应用场景中需要永久存储一些信息（掉电保存数据），如账号、密码或其他配置的一些信息，这些数据的特点是：总量少，但需要灵活存取。像这类情况，就不必使用数据库。我们提供了一套简单的数据存储接口，以键-值对的方式存储。

## 所需头文件

```c++
#include "storage/StoragePreferences.h"
```

## 主要接口

```c++
// 存储接口
static bool putString(const std::string &key, const std::string &val);
static bool putInt(const std::string &key, int val);
static bool putBool(const std::string &key, bool val);
static bool putFloat(const std::string &key, float val);

// 删除指定键
static bool remove(const std::string &key);
// 清空存储数据
static bool clear();

// 获取接口，获取不到对应键值，返回defVal默认值
static std::string getString(const std::string &key, const std::string &defVal);
static int getInt(const std::string &key, int defVal);
static bool getBool(const std::string &key, bool defVal);
static float getFloat(const std::string &key, float defVal);
```

> 警告：该接口是将数据以文件的形式保存在flash中，所以请勿频繁写入，造成flash损坏。该分区大小有限制，屏的型号不同，分区大小也不同。

## 使用示例

### 保存

```c++
//保存字符串，以"username"为别名，值为name字符串
const char* name = "zhang san";
StoragePreferences::putString("username", name);

//保存布尔变量，以"power"为别名，值为true
StoragePreferences::putBool("power", true);

//保存浮点数，以"temperature"为别名，值为30.12
StoragePreferences::putFloat("temperature", 30.12);

//保存整型，以"age"为别名，值为20
StoragePreferences::putInt("age", 20);
```

### 读取

```c++
//读取"username"这个键的值，如果没有值，返回空字符串
std::string name = StoragePreferences::getString("username", "");
LOGD("username %s\n", username.c_str());

//读取布尔变量，如果没有值，则指定返回false
bool power = StoragePreferences::getBool("power", false);

//读取浮点数，如果没有值，则指定返回0
float temperature = StoragePreferences::getFloat("temperature", 0);

//读取整型，如果没有值，则指定返回18
int age = StoragePreferences::getInt("age", 18);
```

### 删除

```c++
//单独清空某一个值
StoragePreferences::remove("username");
StoragePreferences::remove("power");
StoragePreferences::remove("temperature");
StoragePreferences::remove("age");
//清空所有值
StoragePreferences::clear();
```

### 修改
如果需要修改某个值，只需要按键值重复保存即可，将自动覆盖旧的值
