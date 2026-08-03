#include "pet_generated.h"

#define DEMO_W 16
#define DEMO_H 16

typedef struct {
    uint16_t colours[DEMO_W * DEMO_H];
    uint8_t alpha[DEMO_W * DEMO_H];
} demo_map_t;

/* Public fallback: an opaque red square with the same descriptor contract. */
static const LV_ATTRIBUTE_MEM_ALIGN demo_map_t pet_demo_map = {
    .colours = {[0 ... (DEMO_W * DEMO_H - 1)] = 0xF800},
    .alpha = {[0 ... (DEMO_W * DEMO_H - 1)] = 0xFF},
};

static const lv_image_dsc_t pet_demo = {
    .header.magic = LV_IMAGE_HEADER_MAGIC,
    .header.cf = LV_COLOR_FORMAT_RGB565A8,
    .header.flags = 0,
    .header.w = DEMO_W,
    .header.h = DEMO_H,
    .header.stride = DEMO_W * 2,
    .data_size = sizeof(pet_demo_map),
    .data = (const uint8_t *)&pet_demo_map,
};

const lv_image_dsc_t *const PET_FRAMES[PET_FRAME_COUNT] = {
    [0 ... (PET_FRAME_COUNT - 1)] = &pet_demo,
};
