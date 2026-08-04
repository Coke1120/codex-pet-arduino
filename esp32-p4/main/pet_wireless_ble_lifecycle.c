#include "pet_wireless_ble_lifecycle.h"

#include <stddef.h>

void pet_wireless_ble_lifecycle_init(pet_wireless_ble_lifecycle_t *lifecycle)
{
    if (lifecycle == NULL) {
        return;
    }

    *lifecycle = (pet_wireless_ble_lifecycle_t){0};
}

bool pet_wireless_ble_sync_timed_out(int64_t now_us, int64_t deadline_us,
                                     bool enable_requested, bool synced)
{
    return deadline_us > 0 && now_us >= deadline_us && enable_requested && !synced;
}

int32_t pet_wireless_ble_lifecycle_enable(
    pet_wireless_ble_lifecycle_t *lifecycle,
    const pet_wireless_ble_lifecycle_ops_t *ops,
    void *context)
{
    int32_t result;

    if (lifecycle == NULL || ops == NULL) {
        return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
    }

    if (!lifecycle->controller_initialized) {
        if (ops->controller_init == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        lifecycle->controller_initialized = true;
        result = ops->controller_init(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
    }

    if (!lifecycle->controller_enabled) {
        if (ops->controller_enable == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        lifecycle->controller_enabled = true;
        result = ops->controller_enable(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
    }

    if (!lifecycle->host_initialized) {
        if (ops->host_init == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        result = ops->host_init(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        lifecycle->host_initialized = true;
    }

    if (!lifecycle->host_running) {
        if (ops->host_start == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        result = ops->host_start(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        lifecycle->host_running = true;
    }

    return PET_WIRELESS_BLE_LIFECYCLE_OK;
}

int32_t pet_wireless_ble_lifecycle_disable(
    pet_wireless_ble_lifecycle_t *lifecycle,
    const pet_wireless_ble_lifecycle_ops_t *ops,
    void *context)
{
    int32_t result;

    if (lifecycle == NULL || ops == NULL) {
        return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
    }

    if (lifecycle->host_running) {
        if (ops->advertising_stop == NULL || ops->host_stop == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        result = ops->advertising_stop(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        result = ops->host_stop(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        lifecycle->host_running = false;
    }

    if (lifecycle->host_initialized) {
        if (ops->host_deinit == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        result = ops->host_deinit(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        lifecycle->host_initialized = false;
    }

    if (lifecycle->controller_enabled) {
        if (ops->controller_disable == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        result = ops->controller_disable(context);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        lifecycle->controller_enabled = false;
    }

    if (lifecycle->controller_initialized) {
        if (ops->controller_deinit == NULL) {
            return PET_WIRELESS_BLE_LIFECYCLE_INVALID_ARGUMENT;
        }
        result = ops->controller_deinit(context, false);
        if (result != PET_WIRELESS_BLE_LIFECYCLE_OK) {
            return result;
        }
        lifecycle->controller_initialized = false;
    }

    return PET_WIRELESS_BLE_LIFECYCLE_OK;
}
