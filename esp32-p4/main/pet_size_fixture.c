#include "pet_generated.h"

#define PET_SIZE_FIXTURE_FRAME_BYTES (PET_FRAME_W * PET_FRAME_H * 3)
#define PET_SIZE_FIXTURE_TOTAL_BYTES \
    (PET_SIZE_FIXTURE_FRAME_BYTES * PET_FRAME_COUNT)

/* Rights-safe CI payload: one retained object with the exact byte footprint of
 * all 73 RGB565A8 v2 frames. The descriptor array also matches the private
 * translation unit's 73 descriptors, while repeated visual data keeps the
 * fixture content irrelevant. */
static const LV_ATTRIBUTE_MEM_ALIGN uint8_t
    pet_size_fixture_payload[PET_SIZE_FIXTURE_TOTAL_BYTES]
    __attribute__((used)) = {
        [0 ... (PET_SIZE_FIXTURE_TOTAL_BYTES - 1)] = 0xA5,
    };

_Static_assert(PET_SIZE_FIXTURE_TOTAL_BYTES == 6790752,
               "v2 size fixture must match the 73-frame RGB565A8 payload");

static const lv_image_dsc_t pet_size_fixture_images[PET_FRAME_COUNT]
    __attribute__((used)) = {
        [0 ... (PET_FRAME_COUNT - 1)] = {
            .header.magic = LV_IMAGE_HEADER_MAGIC,
            .header.cf = LV_COLOR_FORMAT_RGB565A8,
            .header.flags = 0,
            .header.w = PET_FRAME_W,
            .header.h = PET_FRAME_H,
            .header.stride = PET_FRAME_W * 2,
            .data_size = PET_SIZE_FIXTURE_FRAME_BYTES,
            .data = pet_size_fixture_payload,
        },
};

const lv_image_dsc_t *const PET_FRAMES[PET_FRAME_COUNT] = {
    [0 ... (PET_FRAME_COUNT - 1)] = &pet_size_fixture_images[0],
};
