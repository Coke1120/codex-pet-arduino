function(codex_pet_validate_generated_asset asset_path)
    # ESP-IDF evaluates component requirements in a separate CMake script that
    # does not forward project cache overrides such as CODEX_PET_ASSET_SOURCE.
    # Validate only in the real configure pass, where the selected source is
    # authoritative; a stale local fallback is otherwise mistaken for an
    # explicitly selected external source.
    if(CMAKE_BUILD_EARLY_EXPANSION)
        return()
    endif()
    file(STRINGS "${asset_path}" generated_asset_marker
        LIMIT_COUNT 1
        LIMIT_INPUT 128
    )
    if(NOT generated_asset_marker STREQUAL "// CODEX_PET_GENERATED_ABI: 2")
        message(FATAL_ERROR
            "Codex Pet generated asset uses an unsupported ABI. Regenerate it "
            "with the current tools/convert_codex_pet_p4.py or pass a current "
            "external CODEX_PET_ASSET_SOURCE."
        )
    endif()
endfunction()

if("$ENV{CODEX_PET_SIZE_FIXTURE}" STREQUAL "1")
    set(PET_ASSET_SOURCE "pet_size_fixture.c")
elseif(DEFINED CODEX_PET_ASSET_SOURCE AND NOT CODEX_PET_ASSET_SOURCE STREQUAL "")
    if(NOT IS_ABSOLUTE "${CODEX_PET_ASSET_SOURCE}")
        message(FATAL_ERROR "CODEX_PET_ASSET_SOURCE must be an absolute path")
    endif()
    if(NOT EXISTS "${CODEX_PET_ASSET_SOURCE}")
        message(FATAL_ERROR "CODEX_PET_ASSET_SOURCE does not exist")
    endif()
    set(PET_ASSET_SOURCE "${CODEX_PET_ASSET_SOURCE}")
    codex_pet_validate_generated_asset("${CODEX_PET_ASSET_SOURCE}")
elseif(EXISTS "${CMAKE_CURRENT_LIST_DIR}/pet_generated.c")
    set(PET_ASSET_SOURCE "pet_generated.c")
    codex_pet_validate_generated_asset("${CMAKE_CURRENT_LIST_DIR}/pet_generated.c")
else()
    set(PET_ASSET_SOURCE "pet_demo.c")
endif()

if(DEFINED CODEX_PET_ASSET_SOURCE AND NOT CODEX_PET_ASSET_SOURCE STREQUAL "")
    message(STATUS "Codex Pet asset source: external override")
else()
    message(STATUS "Codex Pet asset source: ${PET_ASSET_SOURCE}")
endif()

idf_component_register(
    SRCS "codex_pet_main.c" "pet_protocol.c" "pet_interaction.c"
         "pet_wireless.c" "pet_wireless_model.c" "pet_wireless_ble_lifecycle.c"
         "${PET_ASSET_SOURCE}"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_uart esp_driver_jpeg esp_timer esp_event esp_netif esp_wifi bt esp_hosted
             lvgl esp32_p4_jc4880p433c_bsp
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -fstack-usage
    -Werror=frame-larger-than=768
)

# Defer ESP-Hosted initialization until app_main has brought up the display.
idf_component_set_property(espressif__esp_hosted WHOLE_ARCHIVE FALSE)
