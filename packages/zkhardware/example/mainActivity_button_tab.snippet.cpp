/****** activity 侧：sButtonCallbackTab 按键注册片段（照抄进 src/activity/mainActivity.cpp） ******
 *  位置：mainActivity.cpp 的 `static S_ButtonCallback sButtonCallbackTab[] = { ... };`
 *  漏了这一步 = 按钮点了没反应（无日志、无结果），是本包最常见的坑。
 *  ID_MAIN_<Caption> 由构建生成（.fun/<平台>/generated/ui_main.h），caption 换名字这里也要跟着换。
 */
static S_ButtonCallback sButtonCallbackTab[] = {
    ID_MAIN_ButtonRelay1, onButtonClick_ButtonRelay1,
    ID_MAIN_ButtonRelay2, onButtonClick_ButtonRelay2,
    ID_MAIN_ButtonRelay3, onButtonClick_ButtonRelay3,
    ID_MAIN_ButtonRelayRead, onButtonClick_ButtonRelayRead,
    ID_MAIN_ButtonRelayAllOff, onButtonClick_ButtonRelayAllOff,
    ID_MAIN_ButtonBeep, onButtonClick_ButtonBeep,
    ID_MAIN_ButtonBrightDown, onButtonClick_ButtonBrightDown,
    ID_MAIN_ButtonBrightUp, onButtonClick_ButtonBrightUp,
    ID_MAIN_ButtonAdc, onButtonClick_ButtonAdc,
};
