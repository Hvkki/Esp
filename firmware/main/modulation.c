// SPDX-License-Identifier: MIT
//
// Синусоїдна обвідна на первинці + розгортка полярності (unfolder).
//
// Логіка одного кроку ISR:
//   1) зсунути фазовий акумулятор на step (задає частоту виходу 20-400 Гц)
//   2) взяти |sin| з таблиці -> duty -> phi_ticks -> у MCPWM (LV + SR)
//   3) на зміні знаку синуса: погасити duty, зробити паузу (blanking),
//      перекинути unfolder, відпустити duty
//
// Unfolder комутує ЛИШЕ на частоті виходу і саме в момент, коли обвідна проходить
// через нуль, тому комутаційні втрати на ньому близькі до нуля.
// ВАЖЛИВО: це справедливо для навантаження з cos(phi) близьким до 1. Для двигуна
// струм у момент нуля напруги НЕ нульовий - див. docs/REVIEW.md, п.7.
#include "modulation.h"
#include "inv_config.h"
#include "pwm.h"
#include "driver/gptimer.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_attr.h"
#include <math.h>

static const char *TAG = "inv_mod";

#define LUT_BITS 10
#define LUT_SIZE (1 << LUT_BITS)

static int16_t  s_lut[LUT_SIZE];              // |sin| у Q15, півперіод
static gptimer_handle_t s_timer;
static const float S_FUPD = (float)INV_CARRIER_HZ / INV_MOD_DECIM;

static volatile uint32_t s_step;              // приріст фази на крок ISR
static volatile uint16_t s_amp_target;
static volatile uint16_t s_amp;               // поточна амплітуда (софт-старт)
static volatile uint16_t s_amp_ramp;          // приріст амплітуди на крок
static volatile float    s_fout;
static volatile uint32_t s_isr_cnt;

static uint32_t s_phase;                      // 0..2^32, один оборот = період виходу
static bool     s_polarity;                   // false = позитивна півхвиля
static uint32_t s_blank;                      // лишилось кроків блокування
static uint32_t s_blank_ticks;

static inline void IRAM_ATTR unfolder_off(void)
{
    gpio_set_level(GPIO_UNF_POS, 0);
    gpio_set_level(GPIO_UNF_NEG, 0);
}
static inline void IRAM_ATTR unfolder_set(bool negative)
{
    gpio_set_level(GPIO_UNF_POS, negative ? 0 : 1);
    gpio_set_level(GPIO_UNF_NEG, negative ? 1 : 0);
}

static bool IRAM_ATTR on_tick(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *arg)
{
    (void)t; (void)e; (void)arg;
    s_isr_cnt++;

    // --- софт-старт / плавне зниження
    uint16_t amp = s_amp, tgt = s_amp_target;
    if (amp < tgt) { amp = (uint16_t)((amp + s_amp_ramp > tgt) ? tgt : amp + s_amp_ramp); }
    else if (amp > tgt) { amp = (uint16_t)((amp < s_amp_ramp) ? 0 : amp - s_amp_ramp); }
    s_amp = amp;

    // --- фаза виходу
    uint32_t prev = s_phase;
    s_phase += s_step;
    bool wrapped_half = ((prev ^ s_phase) & 0x80000000u) != 0;   // перетнули півперіод

    if (wrapped_half) {
        // Перехід через нуль обвідної: гасимо енергію і перекидаємо unfolder із паузою.
        inv_pwm_set_phase(0);
        unfolder_off();
        s_polarity = (s_phase & 0x80000000u) != 0;
        s_blank = s_blank_ticks;
        return false;
    }
    if (s_blank) {
        if (--s_blank == 0) unfolder_set(s_polarity);
        inv_pwm_set_phase(0);
        return false;
    }

    // --- duty з таблиці
    uint32_t idx = (s_phase >> (31 - LUT_BITS)) & (LUT_SIZE - 1);
    uint32_t duty_q15 = ((uint32_t)s_lut[idx] * amp) >> 15;
    uint32_t phi = (duty_q15 * INV_HALF_PERIOD_TICKS) >> 15;
    inv_pwm_set_phase(phi);
    return false;
}

esp_err_t inv_mod_init(void)
{
    for (int i = 0; i < LUT_SIZE; i++) {
        float a = (float)M_PI * ((float)i + 0.5f) / LUT_SIZE;   // 0..pi
        s_lut[i] = (int16_t)lrintf(fabsf(sinf(a)) * 32767.0f);
    }

    gpio_config_t io = {
        .pin_bit_mask = (1ULL << GPIO_UNF_POS) | (1ULL << GPIO_UNF_NEG),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
    unfolder_off();

    s_blank_ticks = (uint32_t)(INV_UNFOLDER_BLANK_US * 1e-6f * S_FUPD);
    if (s_blank_ticks < 1) s_blank_ticks = 1;
    inv_mod_set_out_freq(INV_OUT_FREQ_HZ_DEFAULT);
    s_amp = 0;
    s_amp_target = 0;
    s_amp_ramp = (uint16_t)(INV_DUTY_MAX_Q15 / (INV_SOFTSTART_MS * 1e-3f * S_FUPD)) + 1;

    gptimer_config_t tc = {
        .clk_src       = GPTIMER_CLK_SRC_DEFAULT,
        .direction     = GPTIMER_COUNT_UP,
        .resolution_hz = 10000000,          // 10 МГц, крок 100 нс
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&tc, &s_timer));
    gptimer_alarm_config_t ac = {
        .alarm_count = (uint64_t)(10000000.0f / S_FUPD),
        .reload_count = 0,
        .flags = { .auto_reload_on_alarm = true },
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(s_timer, &ac));
    gptimer_event_callbacks_t cbs = { .on_alarm = on_tick };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(s_timer, &cbs, NULL));
    ESP_ERROR_CHECK(gptimer_enable(s_timer));

    ESP_LOGI(TAG, "f_upd=%.0f Гц, блокування unfolder=%lu кроків, ramp=%u/крок",
             S_FUPD, (unsigned long)s_blank_ticks, s_amp_ramp);
    return ESP_OK;
}

esp_err_t inv_mod_start(void) { return gptimer_start(s_timer); }

void inv_mod_stop(void)
{
    s_amp_target = 0;
    s_amp = 0;
    inv_pwm_set_phase(0);
    gptimer_stop(s_timer);
    unfolder_off();
}

void inv_mod_set_out_freq(float hz)
{
    if (hz < INV_OUT_FREQ_HZ_MIN) hz = INV_OUT_FREQ_HZ_MIN;
    if (hz > INV_OUT_FREQ_HZ_MAX) hz = INV_OUT_FREQ_HZ_MAX;
    s_fout = hz;
    s_step = (uint32_t)(4294967296.0f * hz / S_FUPD);
}

void inv_mod_set_amplitude(uint16_t amp)
{
    if (amp > INV_DUTY_MAX_Q15) amp = INV_DUTY_MAX_Q15;   // жорсткий стелевий обмежувач
    s_amp_target = amp;
}

uint16_t inv_mod_get_amplitude(void) { return s_amp; }
float    inv_mod_get_out_freq(void)  { return s_fout; }
uint32_t inv_mod_get_isr_count(void) { return s_isr_cnt; }
