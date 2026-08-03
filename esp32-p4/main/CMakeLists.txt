if("$ENV{CODEX_PET_SIZE_FIXTURE}" STREQUAL "1")
    set(PET_ASSET_SOURCE "pet_size_fixture.c")
elseif(EXISTS "${CMAKE_CURRENT_LIST_DIR}/pet_generated.c")
    set(PET_ASSET_SOURCE "pet_generated.c")
else()
    set(PET_ASSET_SOURCE "pet_demo.c")
endif()

idf_component_register(
    SRCS "codex_pet_main.c" "pet_protocol.c" "pet_interaction.c"
         "pet_wireless.c" "pet_wireless_model.c" "${PET_ASSET_SOURCE}"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_uart esp_timer esp_event esp_netif esp_wifi bt esp_hosted
             lvgl esp32_p4_jc4880p433c_bsp
)
