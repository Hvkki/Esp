// SPDX-License-Identifier: MIT
//
// LV phase-shift full bridge (MCPWM0) + синхронний випрямляч (MCPWM1).
//
// Форма сигналів (up-count, період T, фазовий зсув phi у діапазоні [0, T/2]):
//
//   LV плече A (ведуче):  HI від 0 до T/2
//   LV плече B (ведене):  HI від phi до phi + T/2
//   -> напруга на первинці = +V на інтервалі [0, phi) і -V на [T/2, T/2+phi)
//   -> duty = 2*phi/T, тому phi у [0, T/2] покриває весь діапазон 0..100%
//      і НІКОЛИ не перетікає за межу періоду (тому не потрібна обробка wrap)
//
//   SR плече 1: HI від 0 до (phi - trail)          <- випрямляє позитивну півхвилю
//   SR плече 2: HI від (T/2 + lead) до (T/2 + phi - trail)
//   -> коли обидва LO, замкнені нижні ключі SR -> freewheel струму дроселя,
//      і саме тому unfolder комутує лише на частоті виходу (50 Гц), а не носія.
//
// Комплементарні пари формуються апаратним модулем dead-time MCPWM.
#include "pwm.h"
#include "inv_config.h"
#include "driver/mcpwm_prelude.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_attr.h"

static const char *TAG = "inv_pwm";

typedef struct {
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t  oper[2];
    mcpwm_cmpr_handle_t  cmp[2][2];   // [плече][компаратор]
    mcpwm_gen_handle_t   gen[2][2];   // [плече][hi/lo]
    mcpwm_fault_handle_t fault;
} bridge_t;

static bridge_t s_lv, s_sr;
static volatile bool s_faulted = false;

// ---------------------------------------------------------------- допоміжне
static esp_err_t make_timer(int group, mcpwm_timer_handle_t *out)
{
    mcpwm_timer_config_t tc = {
        .group_id      = group,
        .clk_src       = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = INV_MCPWM_CLK_HZ,
        .count_mode    = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks  = INV_PERIOD_TICKS,
    };
    return mcpwm_new_timer(&tc, out);
}

// Створює одне плече: 2 компаратори, 2 генератори (hi/lo) з мертвим часом.
// use_tez_for_high = true -> високий рівень виставляється на початку періоду,
// і тоді cmp[0] не використовується для фронту (лишається як резерв).
static esp_err_t make_leg(bridge_t *b, int group, int leg,
                          int gpio_hi, int gpio_lo,
                          bool use_tez_for_high, uint32_t deadtime)
{
    mcpwm_operator_config_t oc = {
        .group_id = group,
        .flags = { .update_gen_action_on_tez = true,
                   .update_dead_time_on_tez  = true },
    };
    ESP_ERROR_CHECK(mcpwm_new_operator(&oc, &b->oper[leg]));
    ESP_ERROR_CHECK(mcpwm_operator_connect_timer(b->oper[leg], b->timer));

    mcpwm_comparator_config_t cc = { .flags = { .update_cmp_on_tez = true } };
    for (int i = 0; i < 2; i++) {
        ESP_ERROR_CHECK(mcpwm_new_comparator(b->oper[leg], &cc, &b->cmp[leg][i]));
        ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(b->cmp[leg][i], 1));
    }

    mcpwm_generator_config_t gc_hi = { .gen_gpio_num = gpio_hi };
    mcpwm_generator_config_t gc_lo = { .gen_gpio_num = gpio_lo };
    ESP_ERROR_CHECK(mcpwm_new_generator(b->oper[leg], &gc_hi, &b->gen[leg][0]));
    ESP_ERROR_CHECK(mcpwm_new_generator(b->oper[leg], &gc_lo, &b->gen[leg][1]));

    // Дії для "сирого" сигналу плеча (до мертвого часу) на генераторі HI.
    if (use_tez_for_high) {
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_timer_event(
            b->gen[leg][0],
            MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                         MCPWM_TIMER_EVENT_EMPTY,
                                         MCPWM_GEN_ACTION_HIGH)));
    } else {
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(
            b->gen[leg][0],
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                           b->cmp[leg][0],
                                           MCPWM_GEN_ACTION_HIGH)));
    }
    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(
        b->gen[leg][0],
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                       b->cmp[leg][1],
                                       MCPWM_GEN_ACTION_LOW)));

    // Комплементарна пара з мертвим часом (канонічна схема з ESP-IDF):
    // HI отримує затримку переднього фронту, LO - інвертований з затримкою заднього.
    mcpwm_dead_time_config_t dt_hi = { .posedge_delay_ticks = deadtime };
    ESP_ERROR_CHECK(mcpwm_generator_set_dead_time(b->gen[leg][0], b->gen[leg][0], &dt_hi));
    mcpwm_dead_time_config_t dt_lo = { .negedge_delay_ticks = deadtime,
                                       .flags = { .invert_output = true } };
    ESP_ERROR_CHECK(mcpwm_generator_set_dead_time(b->gen[leg][0], b->gen[leg][1], &dt_lo));
    return ESP_OK;
}

// Аварійне гальмування: OST (one-shot trip) - вимикається апаратно, без участі CPU,
// і НЕ знімається автоматично. Це саме те, що потрібно для силової частини.
static esp_err_t attach_fault(bridge_t *b, int group)
{
    mcpwm_gpio_fault_config_t fc = {
        .group_id = group,
        .gpio_num = GPIO_FAULT_N,
        .flags = { .active_level = 0, .pull_up = true },
    };
    ESP_ERROR_CHECK(mcpwm_new_gpio_fault(&fc, &b->fault));

    for (int leg = 0; leg < 2; leg++) {
        mcpwm_brake_config_t bc = {
            .fault      = b->fault,
            .brake_mode = MCPWM_OPER_BRAKE_MODE_OST,
            .flags = { .cbc_recover_on_tez = false },
        };
        ESP_ERROR_CHECK(mcpwm_operator_set_brake_on_fault(b->oper[leg], &bc));
        for (int g = 0; g < 2; g++) {
            ESP_ERROR_CHECK(mcpwm_generator_set_action_on_brake_event(
                b->gen[leg][g],
                MCPWM_GEN_BRAKE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                             MCPWM_OPER_BRAKE_MODE_OST,
                                             MCPWM_GEN_ACTION_LOW)));
        }
    }
    return ESP_OK;
}

// ---------------------------------------------------------------- публічне
esp_err_t inv_pwm_init(void)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << GPIO_DRV_ENABLE) | (1ULL << GPIO_LED_RUN) |
                        (1ULL << GPIO_LED_FAULT),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
    gpio_set_level(GPIO_DRV_ENABLE, 0);   // драйвери вимкнені до явного дозволу

    ESP_ERROR_CHECK(make_timer(INV_LV_GROUP, &s_lv.timer));
    ESP_ERROR_CHECK(make_timer(INV_SR_GROUP, &s_sr.timer));

    // LV: плече A стартує з початку періоду, плече B - по компаратору (фазовий зсув)
    ESP_ERROR_CHECK(make_leg(&s_lv, INV_LV_GROUP, 0, GPIO_LV_A_HI, GPIO_LV_A_LO,
                             true,  INV_LV_DEADTIME_TICKS));
    ESP_ERROR_CHECK(make_leg(&s_lv, INV_LV_GROUP, 1, GPIO_LV_B_HI, GPIO_LV_B_LO,
                             false, INV_LV_DEADTIME_TICKS));
    // SR: плече 1 з початку періоду, плече 2 з середини
    ESP_ERROR_CHECK(make_leg(&s_sr, INV_SR_GROUP, 0, GPIO_SR_A_HI, GPIO_SR_A_LO,
                             true,  INV_SR_DEADTIME_TICKS));
    ESP_ERROR_CHECK(make_leg(&s_sr, INV_SR_GROUP, 1, GPIO_SR_B_HI, GPIO_SR_B_LO,
                             false, INV_SR_DEADTIME_TICKS));

    ESP_ERROR_CHECK(attach_fault(&s_lv, INV_LV_GROUP));
    ESP_ERROR_CHECK(attach_fault(&s_sr, INV_SR_GROUP));

    // Фіксовані компаратори: LV плече A завжди вимикається на середині періоду.
    ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(s_lv.cmp[0][1],
                                                       INV_HALF_PERIOD_TICKS));
    inv_pwm_set_phase(0);

    ESP_ERROR_CHECK(mcpwm_timer_enable(s_lv.timer));
    ESP_ERROR_CHECK(mcpwm_timer_enable(s_sr.timer));
    ESP_LOGI(TAG, "period=%d тіків (%.1f кГц), dead-time LV=%d SR=%d тіків",
             INV_PERIOD_TICKS, INV_MCPWM_CLK_HZ / (float)INV_PERIOD_TICKS / 1000.0f,
             INV_LV_DEADTIME_TICKS, INV_SR_DEADTIME_TICKS);
    return ESP_OK;
}

esp_err_t inv_pwm_start(void)
{
    // Обидві групи MCPWM тактуються від одного PLL_160M і мають однаковий період,
    // тому достатньо один раз вирівняти фазу програмним синхросигналом.
    mcpwm_sync_handle_t soft = NULL;
    mcpwm_soft_sync_config_t sc = {};
    ESP_ERROR_CHECK(mcpwm_new_soft_sync_src(&sc, &soft));
    mcpwm_timer_sync_phase_config_t ph = {
        .sync_src    = soft,
        .count_value = 0,
        .direction   = MCPWM_TIMER_DIRECTION_UP,
    };
    ESP_ERROR_CHECK(mcpwm_timer_set_phase_on_sync(s_lv.timer, &ph));
    ESP_ERROR_CHECK(mcpwm_timer_set_phase_on_sync(s_sr.timer, &ph));

    ESP_ERROR_CHECK(mcpwm_timer_start_stop(s_lv.timer, MCPWM_TIMER_START_NO_STOP));
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(s_sr.timer, MCPWM_TIMER_START_NO_STOP));
    ESP_ERROR_CHECK(mcpwm_soft_sync_activate(soft));

    // ВАЖЛИВО: залишковий зсув між групами (кілька тіків через два окремі запису
    // в регістри) треба ОДИН РАЗ виміряти осцилографом і скомпенсувати
    // константами INV_SR_LEAD_TICKS / INV_SR_TRAIL_TICKS.
    return ESP_OK;
}

void IRAM_ATTR inv_pwm_set_phase(uint32_t phi)
{
    if (phi > INV_HALF_PERIOD_TICKS) phi = INV_HALF_PERIOD_TICKS;

    // --- LV плече B: HI на phi, LO на phi + T/2
    mcpwm_comparator_set_compare_value(s_lv.cmp[1][0], phi ? phi : 1);
    mcpwm_comparator_set_compare_value(s_lv.cmp[1][1], phi + INV_HALF_PERIOD_TICKS);

    // --- SR: вікно провідності вужче за вікно первинки на lead/trail
    const uint32_t min_win = INV_SR_DEADTIME_TICKS + 2;
    uint32_t win = (phi > (INV_SR_LEAD_TICKS + INV_SR_TRAIL_TICKS + min_win))
                   ? (phi - INV_SR_TRAIL_TICKS) : 0;
    if (win == 0) {
        // Занадто вузьке вікно: SR не вмикаємо, струм піде через body diode.
        // Це відбувається лише біля нуля синуса, де струм малий.
        mcpwm_comparator_set_compare_value(s_sr.cmp[0][1], 1);
        mcpwm_comparator_set_compare_value(s_sr.cmp[1][0], INV_PERIOD_TICKS - 1);
        mcpwm_comparator_set_compare_value(s_sr.cmp[1][1], INV_PERIOD_TICKS - 1);
        return;
    }
    // плече 1: HI від початку періоду до win
    mcpwm_comparator_set_compare_value(s_sr.cmp[0][1], win);
    // плече 2: HI від T/2 + lead до T/2 + win
    mcpwm_comparator_set_compare_value(s_sr.cmp[1][0],
                                       INV_HALF_PERIOD_TICKS + INV_SR_LEAD_TICKS);
    mcpwm_comparator_set_compare_value(s_sr.cmp[1][1],
                                       INV_HALF_PERIOD_TICKS + win);
}

void inv_pwm_brake(void)
{
    gpio_set_level(GPIO_DRV_ENABLE, 0);
    inv_pwm_set_phase(0);
    mcpwm_timer_start_stop(s_lv.timer, MCPWM_TIMER_STOP_EMPTY);
    mcpwm_timer_start_stop(s_sr.timer, MCPWM_TIMER_STOP_EMPTY);
    s_faulted = true;
    gpio_set_level(GPIO_LED_FAULT, 1);
    gpio_set_level(GPIO_LED_RUN, 0);
}

bool inv_pwm_clear_fault(void)
{
    if (gpio_get_level(GPIO_FAULT_N) == 0) return false;  // аварія ще активна
    s_faulted = false;
    gpio_set_level(GPIO_LED_FAULT, 0);
    return true;
}

bool inv_pwm_faulted(void) { return s_faulted; }
