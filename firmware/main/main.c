// SPDX-License-Identifier: MIT
//
// HF-link інвертор: скелет прошивки для ESP32 / ESP32-S3.
//
// ЩО ЦЕЙ КОД РОБИТЬ:
//   - генерує phase-shift full bridge на LV-мості (MCPWM0)
//   - генерує вікна синхронного випрямляча (MCPWM1), синхронізовані з первинкою
//   - формує синусоїдну обвідну 20-400 Гц і перекидає unfolder на переходах через нуль
//   - вимикається апаратно по виводу FAULT_N (режим OST, без участі CPU)
//
// ЧОГО ЦЕЙ КОД НЕ РОБИТЬ (і що ОБОВ'ЯЗКОВО потрібно додати до роботи на потужності):
//   - зворотний звʼязок по вихідній напрузі/струму (тут чиста розімкнена петля)
//   - адаптивне підстроювання вікон SR по Vds (це має бути аналоговий контур)
//   - контроль температури, precharge, контроль напруги пака, BMS
//   - будь-який захист, крім зовнішнього апаратного компаратора на FAULT_N
//
// ПОРЯДОК ПЕРШОГО ЗАПУСКУ - див. firmware/README.md. Коротко:
// лабораторний БЖ з обмеженням струму, низька напруга, INV_DUTY_MAX_Q15 малий,
// осцилограф на затворах і на первинці, і тільки потім - підйом потужності.
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "inv_config.h"
#include "pwm.h"
#include "modulation.h"

static const char *TAG = "inv";

typedef enum { ST_IDLE, ST_RAMP, ST_RUN, ST_FAULT } state_t;
static state_t s_state = ST_IDLE;

static void enter_fault(const char *why)
{
    ESP_LOGE(TAG, "АВАРІЯ: %s", why);
    inv_mod_stop();
    inv_pwm_brake();
    s_state = ST_FAULT;
}

void app_main(void)
{
    ESP_LOGW(TAG, "=============================================================");
    ESP_LOGW(TAG, " HF-link інвертор, СКЕЛЕТ. duty обмежений на %.1f%%.",
             100.0f * INV_DUTY_MAX_Q15 / 32768.0f);
    ESP_LOGW(TAG, " Не підключати до акумулятора без апаратного захисту струму.");
    ESP_LOGW(TAG, "=============================================================");

    gpio_config_t fin = {
        .pin_bit_mask = (1ULL << GPIO_FAULT_N),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&fin));

    ESP_ERROR_CHECK(inv_pwm_init());
    ESP_ERROR_CHECK(inv_mod_init());

    // Не стартуємо, якщо апаратний захист вже тримає аварію (немає живлення
    // компаратора, обрив, коротке - усе це має блокувати запуск).
    if (gpio_get_level(GPIO_FAULT_N) == 0) {
        enter_fault("FAULT_N активний ще до запуску");
    } else {
        ESP_ERROR_CHECK(inv_pwm_start());
        ESP_ERROR_CHECK(inv_mod_start());
        gpio_set_level(GPIO_DRV_ENABLE, 1);
        inv_mod_set_out_freq(INV_OUT_FREQ_HZ_DEFAULT);
        inv_mod_set_amplitude(INV_DUTY_MAX_Q15);
        s_state = ST_RAMP;
        ESP_LOGI(TAG, "старт: софт-старт %d мс", INV_SOFTSTART_MS);
    }

    uint32_t last_isr = 0;
    while (1) {
        if (gpio_get_level(GPIO_FAULT_N) == 0 && s_state != ST_FAULT) {
            enter_fault("сигнал з апаратного компаратора струму");
        }

        switch (s_state) {
        case ST_RAMP:
            if (inv_mod_get_amplitude() >= INV_DUTY_MAX_Q15) {
                s_state = ST_RUN;
                gpio_set_level(GPIO_LED_RUN, 1);
                ESP_LOGI(TAG, "режим RUN");
            }
            break;
        case ST_RUN: {
            uint32_t n = inv_mod_get_isr_count();
            if (n == last_isr) enter_fault("ISR модуляції зупинився");
            last_isr = n;
            break;
        }
        case ST_FAULT:
            // Знімається тільки вручну: пропав сигнал аварії -> перезапуск живлення.
            if (inv_pwm_clear_fault()) {
                ESP_LOGW(TAG, "аварія знята, потрібен перезапуск для рестарту");
            }
            break;
        default: break;
        }

        ESP_LOGI(TAG, "стан=%d f_out=%.1f Гц amp=%u/%d duty_max=%.1f%% isr=%lu",
                 s_state, inv_mod_get_out_freq(), inv_mod_get_amplitude(),
                 INV_DUTY_MAX_Q15, 100.0f * INV_DUTY_MAX_Q15 / 32768.0f,
                 (unsigned long)inv_mod_get_isr_count());
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
