/****** activity 侧：sButtonCallbackTab 按键注册片段（照抄进 src/activity/mainActivity.cpp） ******
 *  漏了这一步 = 按钮点了没反应（无日志、无结果）。
 *  ID_MAIN_<Caption> 由构建生成在 .fun/<平台>/generated/ui_main.h。
 */
static S_ButtonCallback sButtonCallbackTab[] = {
    ID_MAIN_ButtonParse, onButtonClick_ButtonParse,
    ID_MAIN_ButtonBuild, onButtonClick_ButtonBuild,
    ID_MAIN_ButtonAuto, onButtonClick_ButtonAuto,
};
