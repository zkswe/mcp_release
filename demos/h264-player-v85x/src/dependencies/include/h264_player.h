/*
 * h264_player.h
 *
 *  Created on: 2022年6月21日
 *      Author: ZKSWE Develop Team
 */

#ifndef _MEDIA_H264_PLAYER_H_
#define _MEDIA_H264_PLAYER_H_

#ifdef __cplusplus
extern "C" {
#endif  /* __cplusplus */

#include <stdint.h>

typedef struct _h264_player_t h264_player_t;

enum disp_rot_e {
	E_DISP_ROT_0,
	E_DISP_ROT_90,
	E_DISP_ROT_180,
	E_DISP_ROT_270,
};

enum h264_player_flag_e {
	E_H264_PLAYER_FLAG_STREAM_EOF = 0x01,
	E_H264_PLAYER_FLAG_DISP_UNCACHE = 0x02,
	E_H264_PLAYER_FLAG_SCALE_DOWN_2 = 0x10,  // scale down 1/2
	E_H264_PLAYER_FLAG_SCALE_DOWN_4 = 0x20,  // scale down 1/4
};

typedef struct {
	int fmt;
	int width;
	int height;
	int left;
	int top;
	int right;
	int bottom;
	uint8_t *data0;
	uint8_t *data1;
	uint8_t *data2;
} h264_decode_frame_t;

typedef void (*h264_decode_frame_cb)(h264_decode_frame_t *frame);

int h264_player_init(int w, int h, enum disp_rot_e rot);
int h264_player_init_ex(int w, int h, enum disp_rot_e rot, int flag);
void h264_player_deinit();
void h264_player_set_decode_cb(h264_decode_frame_cb cb);
void h264_player_show();
void h264_player_hide();
void h264_player_set_mirror(int mirror);
void h264_player_set_rot(enum disp_rot_e rot);
void h264_player_set_pos(int x, int y, int w, int h);
void h264_player_set_crop(int x, int y, int w, int h);
void h264_player_put_frame(uint8_t *data, uint32_t size);
int h264_player_get_picture_count();

// 支持多播放实例
h264_player_t* h264_multi_player_create(int w, int h, enum disp_rot_e rot, int flag);
void h264_multi_player_destroy(h264_player_t *player);
void h264_multi_player_set_decode_cb(h264_player_t *player, h264_decode_frame_cb cb);
void h264_multi_player_set_visible(h264_player_t *player, int visible);
void h264_multi_player_set_mirror(h264_player_t *player, int mirror);
void h264_multi_player_set_rot(h264_player_t *player, enum disp_rot_e rot);
void h264_multi_player_set_pos(h264_player_t *player, int x, int y, int w, int h);
void h264_multi_player_set_crop(h264_player_t *player, int x, int y, int w, int h);
int h264_multi_player_put_frame(h264_player_t *player, uint8_t *data, uint32_t size);

#ifdef __cplusplus
}
#endif  /* __cplusplus */

#endif /* _MEDIA_H264_PLAYER_H_ */
