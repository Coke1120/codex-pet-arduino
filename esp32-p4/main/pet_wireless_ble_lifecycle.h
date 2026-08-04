#ifndef PET_WIRELESS_BLE_LIFECYCLE_H
#define PET_WIRELESS_BLE_LIFECYCLE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PET_WIRELESS_BLE_LIFECYCLE_OK INT32_C(0)
#define PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT INT32_C(-1)

typedef struct {
    int32_t (*controller_init)(void *context);
    int32_t (*controller_enable)(void *context);
    int32_t (*host_init)(void *context);
    int32_t (*host_start)(void *context);
    int32_t (*advertising_stop)(void *context);
    int32_t (*host_stop)(void *context);
    int32_t (*host_deinit)(void *context);
    int32_t (*controller_disable)(void *context);
    int32_t (*controller_deinit)(void *context, bool release_memory);
} pet_wireless_ble_lifecycle_ops_t;

typedef struct {
    bool controller_initialized;
    bool controller_enabled;
    bool host_initialized;
    bool host_running;
} pet_wireless_ble_lifecycle_t;

void pet_wireless_ble_lifecycle_init(pet_wireless_ble_lifecycle_t *lifecycle);

bool pet_wireless_ble_sync_timed_out(int64_t now_us, int64_t deadline_us,
                                     bool enable_requested, bool synced);

/*
 * Enables each inactive layer in dependency order. Controller stages are marked
 * before their RPC because ESP-Hosted can fail after changing remote state; a
 * later disable must therefore unwind every attempted controller stage.
 */
int32_t pet_wireless_ble_lifecycle_enable(
    pet_wireless_ble_lifecycle_t *lifecycle,
    const pet_wireless_ble_lifecycle_ops_t *ops,
    void *context);

/*
 * Tears down each active layer in reverse dependency order. Controller memory
 * is retained so a later enable can initialize the controller again safely.
 */
int32_t pet_wireless_ble_lifecycle_disable(
    pet_wireless_ble_lifecycle_t *lifecycle,
    const pet_wireless_ble_lifecycle_ops_t *ops,
    void *context);

#ifdef __cplusplus
}
#endif

#endif
