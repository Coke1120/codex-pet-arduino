#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "pet_wireless_ble_lifecycle.h"

enum {
    MAX_CALLS = 32,
    TEST_FAILURE = 37,
};

typedef enum {
    CALL_CONTROLLER_INIT = 1,
    CALL_CONTROLLER_ENABLE,
    CALL_HOST_INIT,
    CALL_HOST_START,
    CALL_ADVERTISING_STOP,
    CALL_HOST_STOP,
    CALL_HOST_DEINIT,
    CALL_CONTROLLER_DISABLE,
    CALL_CONTROLLER_DEINIT,
} call_t;

typedef struct {
    call_t calls[MAX_CALLS];
    size_t call_count;
    call_t fail_call;
    unsigned int failures_remaining;
    bool remote_controller_initialized;
    bool remote_controller_enabled;
    bool controller_deinit_release_memory;
} fake_backend_t;

static int32_t record_call(fake_backend_t *backend, call_t call)
{
    assert(backend->call_count < MAX_CALLS);
    backend->calls[backend->call_count++] = call;
    if (backend->fail_call == call && backend->failures_remaining > 0U) {
        --backend->failures_remaining;
        return TEST_FAILURE;
    }
    return PET_WIRELESS_BLE_LIFECYCLE_OK;
}

#define DEFINE_FAKE_OP(name, call)                \
    static int32_t name(void *context)             \
    {                                               \
        return record_call(context, call);          \
    }

DEFINE_FAKE_OP(fake_host_init, CALL_HOST_INIT)
DEFINE_FAKE_OP(fake_host_start, CALL_HOST_START)
DEFINE_FAKE_OP(fake_advertising_stop, CALL_ADVERTISING_STOP)
DEFINE_FAKE_OP(fake_host_stop, CALL_HOST_STOP)
DEFINE_FAKE_OP(fake_host_deinit, CALL_HOST_DEINIT)

static int32_t fake_controller_init(void *context)
{
    fake_backend_t *backend = context;
    backend->remote_controller_initialized = true;
    return record_call(backend, CALL_CONTROLLER_INIT);
}

static int32_t fake_controller_enable(void *context)
{
    fake_backend_t *backend = context;
    backend->remote_controller_enabled = true;
    return record_call(backend, CALL_CONTROLLER_ENABLE);
}

static int32_t fake_controller_disable(void *context)
{
    fake_backend_t *backend = context;
    const int32_t result = record_call(backend, CALL_CONTROLLER_DISABLE);
    if (result == PET_WIRELESS_BLE_LIFECYCLE_OK) {
        backend->remote_controller_enabled = false;
    }
    return result;
}

static int32_t fake_controller_deinit(void *context, bool release_memory)
{
    fake_backend_t *backend = context;
    backend->controller_deinit_release_memory = release_memory;
    const int32_t result = record_call(backend, CALL_CONTROLLER_DEINIT);
    if (result == PET_WIRELESS_BLE_LIFECYCLE_OK) {
        backend->remote_controller_enabled = false;
        backend->remote_controller_initialized = false;
    }
    return result;
}

static const pet_wireless_ble_lifecycle_ops_t FAKE_OPS = {
    .controller_init = fake_controller_init,
    .controller_enable = fake_controller_enable,
    .host_init = fake_host_init,
    .host_start = fake_host_start,
    .advertising_stop = fake_advertising_stop,
    .host_stop = fake_host_stop,
    .host_deinit = fake_host_deinit,
    .controller_disable = fake_controller_disable,
    .controller_deinit = fake_controller_deinit,
};

static void assert_calls(const fake_backend_t *backend, const call_t *expected, size_t count)
{
    assert(backend->call_count == count);
    assert(memcmp(backend->calls, expected, count * sizeof(expected[0])) == 0);
}

static void assert_enabled(const pet_wireless_ble_lifecycle_t *lifecycle)
{
    assert(lifecycle->controller_initialized);
    assert(lifecycle->controller_enabled);
    assert(lifecycle->host_initialized);
    assert(lifecycle->host_running);
}

static void assert_disabled(const pet_wireless_ble_lifecycle_t *lifecycle)
{
    assert(!lifecycle->controller_initialized);
    assert(!lifecycle->controller_enabled);
    assert(!lifecycle->host_initialized);
    assert(!lifecycle->host_running);
}

static void test_enable_disable_order_and_reinitialize(void)
{
    const call_t expected_first_cycle[] = {
        CALL_CONTROLLER_INIT,
        CALL_CONTROLLER_ENABLE,
        CALL_HOST_INIT,
        CALL_HOST_START,
        CALL_ADVERTISING_STOP,
        CALL_HOST_STOP,
        CALL_HOST_DEINIT,
        CALL_CONTROLLER_DISABLE,
        CALL_CONTROLLER_DEINIT,
    };
    const call_t expected_second_enable[] = {
        CALL_CONTROLLER_INIT,
        CALL_CONTROLLER_ENABLE,
        CALL_HOST_INIT,
        CALL_HOST_START,
    };
    pet_wireless_ble_lifecycle_t lifecycle;
    fake_backend_t backend = {0};

    pet_wireless_ble_lifecycle_init(&lifecycle);
    assert_disabled(&lifecycle);

    assert(pet_wireless_ble_lifecycle_enable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_enabled(&lifecycle);

    /* The host is idle (not advertising), but OFF must still tear it down. */
    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_disabled(&lifecycle);
    assert(!backend.controller_deinit_release_memory);
    assert_calls(&backend, expected_first_cycle,
                 sizeof(expected_first_cycle) / sizeof(expected_first_cycle[0]));

    memset(&backend, 0, sizeof(backend));
    assert(pet_wireless_ble_lifecycle_enable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_enabled(&lifecycle);
    assert_calls(&backend, expected_second_enable,
                 sizeof(expected_second_enable) / sizeof(expected_second_enable[0]));
}

static void test_sync_timeout_requires_an_expired_pending_enable(void)
{
    assert(!pet_wireless_ble_sync_timed_out(100, 0, true, false));
    assert(!pet_wireless_ble_sync_timed_out(99, 100, true, false));
    assert(!pet_wireless_ble_sync_timed_out(100, 100, false, false));
    assert(!pet_wireless_ble_sync_timed_out(100, 100, true, true));
    assert(pet_wireless_ble_sync_timed_out(100, 100, true, false));
}

static void test_enable_failure_resumes_at_failed_stage(void)
{
    const call_t expected[] = {
        CALL_CONTROLLER_INIT,
        CALL_CONTROLLER_ENABLE,
        CALL_HOST_INIT,
        CALL_HOST_INIT,
        CALL_HOST_START,
    };
    pet_wireless_ble_lifecycle_t lifecycle;
    fake_backend_t backend = {
        .fail_call = CALL_HOST_INIT,
        .failures_remaining = 1U,
    };

    pet_wireless_ble_lifecycle_init(&lifecycle);
    assert(pet_wireless_ble_lifecycle_enable(&lifecycle, &FAKE_OPS, &backend) == TEST_FAILURE);
    assert(lifecycle.controller_initialized);
    assert(lifecycle.controller_enabled);
    assert(!lifecycle.host_initialized);
    assert(!lifecycle.host_running);

    assert(pet_wireless_ble_lifecycle_enable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_enabled(&lifecycle);
    assert_calls(&backend, expected, sizeof(expected) / sizeof(expected[0]));
}

static void test_disable_failure_preserves_active_stage(void)
{
    const call_t expected[] = {
        CALL_ADVERTISING_STOP,
        CALL_HOST_STOP,
        CALL_HOST_DEINIT,
        CALL_HOST_DEINIT,
        CALL_CONTROLLER_DISABLE,
        CALL_CONTROLLER_DEINIT,
    };
    pet_wireless_ble_lifecycle_t lifecycle = {
        .controller_initialized = true,
        .controller_enabled = true,
        .host_initialized = true,
        .host_running = true,
    };
    fake_backend_t backend = {
        .fail_call = CALL_HOST_DEINIT,
        .failures_remaining = 1U,
    };

    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == TEST_FAILURE);
    assert(lifecycle.controller_initialized);
    assert(lifecycle.controller_enabled);
    assert(lifecycle.host_initialized);
    assert(!lifecycle.host_running);

    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_disabled(&lifecycle);
    assert(!backend.controller_deinit_release_memory);
    assert_calls(&backend, expected, sizeof(expected) / sizeof(expected[0]));
}

static void test_host_stop_failure_retries_without_skipping_teardown(void)
{
    const call_t expected[] = {
        CALL_ADVERTISING_STOP,
        CALL_HOST_STOP,
        CALL_ADVERTISING_STOP,
        CALL_HOST_STOP,
        CALL_HOST_DEINIT,
        CALL_CONTROLLER_DISABLE,
        CALL_CONTROLLER_DEINIT,
    };
    pet_wireless_ble_lifecycle_t lifecycle = {
        .controller_initialized = true,
        .controller_enabled = true,
        .host_initialized = true,
        .host_running = true,
    };
    fake_backend_t backend = {
        .fail_call = CALL_HOST_STOP,
        .failures_remaining = 1U,
    };

    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == TEST_FAILURE);
    assert_enabled(&lifecycle);

    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_disabled(&lifecycle);
    assert(!backend.controller_deinit_release_memory);
    assert_calls(&backend, expected, sizeof(expected) / sizeof(expected[0]));
}

static void test_controller_init_failure_still_unwinds_remote_side_effect(void)
{
    const call_t expected[] = {
        CALL_CONTROLLER_INIT,
        CALL_CONTROLLER_DEINIT,
    };
    pet_wireless_ble_lifecycle_t lifecycle;
    fake_backend_t backend = {
        .fail_call = CALL_CONTROLLER_INIT,
        .failures_remaining = 1U,
    };

    pet_wireless_ble_lifecycle_init(&lifecycle);
    assert(pet_wireless_ble_lifecycle_enable(&lifecycle, &FAKE_OPS, &backend) ==
           TEST_FAILURE);
    assert(lifecycle.controller_initialized);
    assert(!lifecycle.controller_enabled);
    assert(backend.remote_controller_initialized);

    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_disabled(&lifecycle);
    assert(!backend.remote_controller_initialized);
    assert(!backend.remote_controller_enabled);
    assert(!backend.controller_deinit_release_memory);
    assert_calls(&backend, expected, sizeof(expected) / sizeof(expected[0]));
}

static void test_controller_enable_failure_still_unwinds_remote_side_effect(void)
{
    const call_t expected[] = {
        CALL_CONTROLLER_INIT,
        CALL_CONTROLLER_ENABLE,
        CALL_CONTROLLER_DISABLE,
        CALL_CONTROLLER_DEINIT,
    };
    pet_wireless_ble_lifecycle_t lifecycle;
    fake_backend_t backend = {
        .fail_call = CALL_CONTROLLER_ENABLE,
        .failures_remaining = 1U,
    };

    pet_wireless_ble_lifecycle_init(&lifecycle);
    assert(pet_wireless_ble_lifecycle_enable(&lifecycle, &FAKE_OPS, &backend) ==
           TEST_FAILURE);
    assert(lifecycle.controller_initialized);
    assert(lifecycle.controller_enabled);
    assert(backend.remote_controller_initialized);
    assert(backend.remote_controller_enabled);

    assert(pet_wireless_ble_lifecycle_disable(&lifecycle, &FAKE_OPS, &backend) == 0);
    assert_disabled(&lifecycle);
    assert(!backend.remote_controller_initialized);
    assert(!backend.remote_controller_enabled);
    assert(!backend.controller_deinit_release_memory);
    assert_calls(&backend, expected, sizeof(expected) / sizeof(expected[0]));
}

int main(void)
{
    test_enable_disable_order_and_reinitialize();
    test_sync_timeout_requires_an_expired_pending_enable();
    test_enable_failure_resumes_at_failed_stage();
    test_disable_failure_preserves_active_stage();
    test_host_stop_failure_retries_without_skipping_teardown();
    test_controller_init_failure_still_unwinds_remote_side_effect();
    test_controller_enable_failure_still_unwinds_remote_side_effect();
    puts("pet_wireless_ble_lifecycle tests passed");
    return 0;
}
