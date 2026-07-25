idf_component_register(
    SRCS "main.c" "pwm.c" "modulation.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_driver_mcpwm esp_driver_gptimer esp_driver_gpio
)
