/* zk_vinyl_circle_mask.h - 正圆覆盖率表（0..255 = 该像素被圆覆盖的面积比例） */
#ifndef _ZK_VINYL_CIRCLE_MASK_H_
#define _ZK_VINYL_CIRCLE_MASK_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** 返回 size*size 的覆盖率表（malloc 出来的，调用方 free）；失败返回 NULL。
 *  口径：SS=8 子采样面积平均（与工程静态圆封面同源），无浮点。 */
uint8_t *zk_vinyl_circle_mask(int size);

#ifdef __cplusplus
}
#endif

#endif /* _ZK_VINYL_CIRCLE_MASK_H_ */
