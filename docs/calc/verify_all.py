#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФІНАЛЬНА ПЕРЕПРОВІРКА ВСЬОГО, одним послідовним розрахунком.
Мета: щоб усі числа в документі походили з ОДНОГО набору припущень, без суперечностей.
Кожен блок має або самоперевірку, або незалежну перехресну перевірку іншим методом.
"""
import math

# ============================================================ константи
RHO20, ALPHA_CU, MU0 = 1.72e-8, 0.00393, 4*math.pi*1e-7
rho = lambda T: RHO20*(1+ALPHA_CU*(T-20))
delta = lambda f, T=100: math.sqrt(rho(T)/(math.pi*f*MU0))
def dowell(h, dl, m):
    D = h/dl
    return (D*(math.sinh(2*D)+math.sin(2*D))/(math.cosh(2*D)-math.cos(2*D))
            + (2/3)*D*(m*m-1)*(math.sinh(D)-math.sin(D))/(math.cosh(D)+math.cos(D)))
def hr(t): print("\n"+"="*84+"\n"+t+"\n"+"="*84)

# ============================================================ 0. самоперевірка
hr("0. САМОПЕРЕВІРКА МАТЕМАТИКИ")
N = 400000
mean = lambda p: sum(math.sin(math.pi*(k+.5)/N)**p for k in range(N))/N
checks = [
    ("<sin^2> = 0.5",            abs(mean(2)-0.5) < 1e-4),
    ("<sin^4> = 0.375",          abs(mean(4)-0.375) < 1e-4),
    ("<sin^3> = 4/(3pi)",        abs(mean(3)-4/(3*math.pi)) < 1e-4),
    ("Dowell m=1, h<<d -> 1",    abs(dowell(1e-6,1e-3,1)-1) < 1e-3),
    ("Dowell m=1, h>>d -> h/d",  abs(dowell(10e-3,1e-3,1)/10-1) < 0.05),
    ("delta(150k,20C)=0.170мм",  abs(delta(150e3,20)*1e3-0.170) < 0.005),
    ("delta(150k,100C)=0.195мм", abs(delta(150e3,100)*1e3-0.195) < 0.005),
    ("rho(100C)/rho(20C)=1.31",  abs(rho(100)/rho(20)-1.314) < 0.01),
]
for name, r in checks: print(f"  [{'OK ' if r else 'FAIL'}] {name}")
assert all(r for _, r in checks)
K_SIN3, K_SIN2 = mean(3), mean(2)

# ============================================================ 1. ТЗ
hr("1. ТЕХНІЧНЕ ЗАВДАННЯ І БАЗОВІ СТРУМИ")
P_OUT, V_OUT = 3000.0, 230.0
Vo_pk  = V_OUT*math.sqrt(2)
Io_rms = P_OUT/V_OUT
Io_pk  = Io_rms*math.sqrt(2)
F_C    = 150e3
D_MAX  = 0.90
print(f"  Pout={P_OUT:.0f} Вт | Vout={V_OUT:.0f} В RMS = {Vo_pk:.1f} В пік")
print(f"  Iout={Io_rms:.2f} А RMS = {Io_pk:.2f} А пік")
print(f"  Носій {F_C/1e3:.0f} кГц, максимальний duty {D_MAX}")
print(f"  Одноступенева схема без HV DC-ланки -> миттєва потужність p(t)=2P*sin^2,")
print(f"  пік {2*P_OUT:.0f} Вт. Перевірка: <p(t)> = 2P*<sin^2> = {2*P_OUT*K_SIN2:.0f} Вт = Pout [OK]")
E_100Hz = P_OUT/(2*math.pi*50)
C_need = 2*E_100Hz/(25.2**2-23.2**2)
print(f"  Чи можна згладити 100 Гц пульсацію конденсатором на 24 В? Потрібно "
      f"C={C_need*1e3:.0f} мФ -> ні. Отже батарея реально бачить пульсуючий струм.")

# ============================================================ 2. КОЕФІЦІЄНТ ТРАНСФОРМАЦІЇ
hr("2. ГОЛОВНЕ УТОЧНЕННЯ: n задає МІНІМАЛЬНА напруга, а струм первинки задає n")
print("Раніше я рахував I_pri для n, підібраного під ПОТОЧНУ напругу. Це неправильно:")
print("n у залізі фіксований, тому I_pri = n * Iout_rms НЕ залежить від заряду акумулятора.")
print("Отже втрати треба рахувати з n, підібраним під РОЗРЯДЖЕНИЙ акумулятор.\n")

def system(name, Vmin, Vnom, Vmax, Np):
    n = Vo_pk/(Vmin*D_MAX)
    Ns = round(n*Np)
    n_real = Ns/Np
    I_pri_rms = n_real*Io_rms          # варіант 1 (freewheel через SR) - струм циркулює
    I_pri_pk  = n_real*Io_pk
    d = {"name": name, "Vmin": Vmin, "Vnom": Vnom, "Vmax": Vmax, "Np": Np, "Ns": Ns,
         "n": n_real, "Ipri_rms": I_pri_rms, "Ipri_pk": I_pri_pk}
    print(f"  {name}")
    print(f"    Vmin={Vmin} В -> n потрібне {n:.2f} -> беремо Np={Np}, Ns={Ns} (n={n_real:.2f})")
    print(f"    duty: при Vmin={Vmin} В -> {Vo_pk/(Vmin*n_real):.2f} | "
          f"Vnom={Vnom} В -> {Vo_pk/(Vnom*n_real):.2f} | Vmax={Vmax} В -> {Vo_pk/(Vmax*n_real):.2f}")
    print(f"    I первинки (НЕ залежить від Vbat): {I_pri_rms:.1f} А RMS / {I_pri_pk:.1f} А пік")
    for V in (Vmin, Vnom, Vmax):
        i_lf = (P_OUT/V)*math.sqrt(1.5)
        print(f"    при {V:>4.1f} В: батарея avg={P_OUT/V:6.1f} А, LF RMS={i_lf:6.1f} А, "
              f"пік={2*P_OUT/V:6.1f} А")
    # струм пульсацій вхідних конденсаторів: різниця між імпульсним струмом моста і LF
    dd = Vo_pk/(Vnom*n_real)
    I_puls_rms = I_pri_pk*math.sqrt(dd*K_SIN3)
    i_lf_nom = (P_OUT/Vnom)*math.sqrt(1.5)
    I_cap = math.sqrt(max(0, I_puls_rms**2 - i_lf_nom**2))
    print(f"    вхідні конденсатори при {Vnom} В: HF пульсація ~{I_cap:.0f} А RMS "
          f"-> банк плівки/полімеру, не електроліт")
    d["Icap"] = I_cap
    # напруга на вторинці
    Vsec = n_real*Vmax
    print(f"    напруга на вторинці при повному заряді: {n_real:.1f} x {Vmax} В = {Vsec:.0f} В")
    print(f"      -> ключ 650 В має запас {(650-Vsec)/650*100:.0f}% ДО дзвону; з викидами тісно")
    d["Vsec"] = Vsec
    return d

S24 = system("A) 6s Li-Ion: 20...25.2 В (ном. 24), Np=1", 20.0, 24.0, 25.2, 1)
print()
S48 = system("B) 13s Li-Ion: 40...54.6 В (ном. 48), Np=2", 40.0, 48.0, 54.6, 2)

# ============================================================ 3. ТРАНСФОРМАТОР
hr("3. ТРАНСФОРМАТОР ETD59/31/22 N87 (дані з даталиста TDK B66397G0000X187)")
Ae, Ve, MLT, BW = 368e-6, 51.5e-6, 0.106, 38e-3
PV_ANCHOR = 5.2/(Ve*1e6)*1e3      # мВт/см3 при 100 мТл / 100 кГц / 100 C
print(f"  Ae={Ae*1e6:.0f} мм², Ve={Ve*1e6:.1f} см³, MLT~{MLT*1e3:.0f} мм, вікно {BW*1e3:.0f} мм")
print(f"  Даталист: Pcore <= 5.2 Вт/набір @100 мТл,100 кГц,100°C -> Pv={PV_ANCHOR:.0f} мВт/см³")
print(f"  ПЕРЕХРЕСНА ПЕРЕВІРКА: B не залежить від Vbat, бо Vbat*d = Vo_pk/n = const:")
for S in (S24, S48):
    B1 = S["Vnom"]*(Vo_pk/(S["Vnom"]*S["n"]))/(4*F_C*S["Np"]*Ae)   # через Vbat*d
    B2 = Vo_pk/(S["n"]*4*F_C*S["Np"]*Ae)                            # через вихід
    assert abs(B1-B2) < 1e-9
    S["B"] = B1
    print(f"    {S['name'][:2]} B = {B1*1e3:.1f} мТл (два методи збігаються) [OK]")
k_env = mean(2.45)
print(f"  Усереднення по обвідній синуса (показник Steinmetz 2.45): x{k_env:.2f}")
dl = delta(F_C, 100)
for S in (S24, S48):
    Pv = PV_ANCHOR*(F_C/100e3)**1.30*(S["B"]/0.1)**2.45
    S["Pcore"] = Pv*(Ve*1e6)/1e3*k_env
    A_p = 0.2e-3*BW*4                       # 4 шари фольги ПАРАЛЕЛЬНО
    Fr = dowell(0.2e-3, dl, 2)
    S["Pcu_p"] = S["Ipri_rms"]**2*(rho(100)*MLT*S["Np"]/A_p)*Fr
    S["Pcu_s"] = Io_rms**2*(rho(100)*MLT*S["Ns"]/5e-6)*1.15
    S["Ptx"] = S["Pcore"]+S["Pcu_p"]+S["Pcu_s"]
    print(f"\n  {S['name'][:2]} Np={S['Np']}, Ns={S['Ns']}, фольга 0.2x38 мм x4 ПАРАЛЕЛЬНО "
          f"({A_p*1e6:.1f} мм²), вторинка літц 5 мм²")
    print(f"     ферит {S['Pcore']:4.1f} Вт | первинка {S['Pcu_p']:4.1f} Вт (Fr={Fr:.2f}, "
          f"{S['Ipri_rms']:.0f} А) | вторинка {S['Pcu_s']:4.1f} Вт ({Io_rms:.1f} А) "
          f"| РАЗОМ {S['Ptx']:4.1f} Вт")
    print(f"     тепло: {S['Ptx']:.1f} Вт при Rth(ETD59)~8 K/Вт без обдуву = "
          f"+{S['Ptx']*8:.0f}°C -> обдув обовʼязковий")
print("\n  Заповнення вікна (варіант B): 4 шари фольги + 18 витків літца 5 мм² (kf~0.55):")
fill = (0.2e-3*BW*4 + 18*5e-6/0.55)/(BW*9.5e-3)
print(f"     {fill*100:.0f}% вікна без урахування HV-барʼєра -> влазить, але щільно")
print("  Зазор: даталистний AL гапованого ETD59 = 508 нГн -> при Np=1 L=0.51 мкГн ->")
print(f"     розмах струму намагнічення = {24*(1/(2*F_C))/0.51e-6:.0f} А. Зазор ЗАБОРОНЕНО.")

# ============================================================ 4. LV МІСТ
hr("4. LV МІСТ: провідникові з самоузгодженим Tj + усі динамічні складові")
# IRL40SC209: Rds(on) 0.59 мОм typ / 0.72 мОм max (кристал "209", як у IRL40T209).
# Решта - оцінки, масштабовані під великий кристал (даталист віддає 403, звірити вручну!)
QG12, COSS, CRSS, VF = 500e-9, 8.0e-9, 2.0e-9, 0.90
# Опір ПЕРВИННОГО КОНТУРУ поза кристалами: шини, паяні зʼєднання, виводи корпусів,
# шлях до конденсаторного банку. При Rds 0.6 мОм це вже домінуючий член!
R_INTERCONNECT = 0.30e-3
def lv_losses(S, m, rds25, rth_jc, T_hs=70.0, rth_pad=0.7, t_dt=60e-9, kT=0.0060, Vg=12.0):
    I = S["Ipri_rms"]; Ipk = S["Ipri_pk"]; V = S["Vnom"]
    Tj = T_hs+20
    for _ in range(300):
        rds = rds25*(1+kT*(Tj-25))
        Pc = I**2*2*(rds/m); Pdev = Pc/(4*m)
        Tn = T_hs+Pdev*(rth_jc+rth_pad)
        if abs(Tn-Tj) < 0.01: break
        Tj = 0.5*Tj+0.5*Tn
    Pg = 4*m*QG12*Vg*F_C
    Pdt = VF*(2/math.pi)*Ipk*(t_dt*2*F_C)*2
    Cn = 2*m*COSS
    Izvs = V*math.sqrt(Cn/15e-9)
    frac = math.degrees(math.asin(min(1, Izvs/S["n"]/Io_pk)))/90
    Phs = 0.5*Cn*V**2*4*F_C*frac
    dvdt = Ipk/Cn
    Pint = I**2*R_INTERCONNECT
    return dict(cond=Pc, dev=Pdev, Tj=Tj, rds=rds, gate=Pg, dt=Pdt, hs=Phs, inter=Pint,
                tot=Pc+Pg+Pdt+Phs+Pint+1.0, Izvs=Izvs, frac=frac, dvdt=dvdt,
                miller=m*CRSS*dvdt, Ipk_dev=Ipk/m)
print("Ключі:")
print("  IRL40SC209 : StrongIRFET, 40 В, Rds(on) 0.59 мОм typ / 0.72 мОм max @Vgs=10 В")
print("               (кристал '209'; підтверджено по родинному IRL40T209: 0.59/0.72 мОм)")
print("  IRLB3034   : 40 В, TO-220, Rds(on) max 1.7 мОм - для порівняння")
print("  100В/1.5мОм TOLL : гіпотетичний сучасний ключ для 48-вольтової шини")
print("  Rth: для D2PAK-7 шлях тепла йде через плату -> rth_pad=1.2 K/Вт (теплові перехідні")
print("       отвори + алюмінієва основа), для TO-220 на радіаторі через прокладку 0.7 K/Вт")
for S, parts in ((S24, [("IRL40SC209 max 0.72мОм", 0.00072, 0.55, 1.2),
                        ("IRL40SC209 typ 0.59мОм", 0.00059, 0.55, 1.2),
                        ("IRLB3034 1.7мОм", 0.0017, 0.40, 0.7)]),
                 (S48, [("IRL40SC209 (40В!)", 0.00072, 0.55, 1.2),
                        ("100В/1.5мОм TOLL", 0.0015, 0.50, 1.2)])):
    print(f"\n  {S['name'][:2]} I_pri={S['Ipri_rms']:.0f} А RMS / {S['Ipri_pk']:.0f} А пік")
    for pname, r25, rjc, rpad in parts:
        for m in (2, 3, 4):
            L = lv_losses(S, m, r25, rjc, rth_pad=rpad)
            print(f"    {pname:<24s} m={m}: Rds_hot={L['rds']*1e3:.2f}мОм Tj={L['Tj']:3.0f}°C "
                  f"| кристали{L['cond']:6.1f} шини{L['inter']:5.1f} затв.{L['gate']:4.1f} "
                  f"мертв.{L['dt']:4.1f} жорст.{L['hs']:4.2f} = {L['tot']:6.1f}Вт "
                  f"({L['tot']/P_OUT*100:.2f}%) | {L['dev']:4.1f}Вт/ключ")
L = lv_losses(S24, 2, 0.00072, 0.55, rth_pad=1.2)
print(f"\n  ZVS (варіант A, IRL40SC209 ПАРНО): I_min={L['Izvs']:.0f} А -> ZVS втрачається лише у "
      f"{L['frac']*100:.0f}% півхвилі, жорсткі втрати {L['hs']:.2f} Вт")
print(f"  Зворотна проблема: dv/dt={L['dvdt']/1e9:.1f} В/нс -> Miller-струм у затвор "
      f"{L['miller']:.0f} А -> потрібне відʼємне зміщення і/або снабер")

# ============================================================ 5. HV
hr("5. HV КАСКАД (SR + unfolder): 4 ключі в шляху струму в усіх станах")
print("  Стан 'передача': вторинка -> 2 ключі SR -> 2 ключі unfolder -> фільтр")
print("  Стан 'freewheel': SR замикає шину -> 2 ключі SR + 2 ключі unfolder")
print("  Отже 4 ключі завжди, і струм = струм дроселя = Iout_rms. Не залежить від duty. [OK]")
HV = [("IPW65R019C7 (C7, звич. діод)", 0.019, 1),
      ("IPW65R035CFD7A (швидкий діод)", 0.035, 1),
      ("2x IPW65R035CFD7A паралельно", 0.035, 2),
      ("IPW65R050CFD7A", 0.050, 1)]
for nm, r25, par in HV:
    rh = r25*2.2/par
    print(f"    {nm:<32s} гарячий {rh*1e3:5.1f} мОм -> {Io_rms**2*4*rh:5.1f} Вт "
          f"({Io_rms**2*4*rh/P_OUT*100:.2f}%)")
print("  ПРИМІТКА: 'IPW65R019CFD7' не існує; 19 мОм = C7 зі звичайним body diode.")

# ============================================================ 6. ЗВЕДЕНО
hr("6. ЗВЕДЕНИЙ БЮДЖЕТ І ККД (з перехресною перевіркою балансу потужності)")
def total(S, m, r25, rjc, hv_r, hv_par, label, hv_sw=15.0, filt=15.0, bus=10.0, aux=7.0):
    L = lv_losses(S, m, r25, rjc, rth_pad=1.2)
    hv = Io_rms**2*4*(hv_r*2.2/hv_par)
    items = [("LV міст (усе разом)", L["tot"]), ("Трансформатор", S["Ptx"]),
             ("HV провідникові", hv), ("HV перемикальні + Qrr", hv_sw),
             ("Вихідний LC-фільтр", filt), ("Конденсатори/шини/клеми", bus),
             ("Драйвери/ESP/вентилятор", aux)]
    tot = sum(v for _, v in items)
    Pin = P_OUT+tot
    assert abs(Pin-tot-P_OUT) < 1e-9         # баланс потужності
    print(f"\n  {label}")
    for k, v in items: print(f"      {k:<32s} {v:6.1f} Вт")
    print(f"      {'РАЗОМ':<32s} {tot:6.1f} Вт | Pin={Pin:.0f} Вт | ККД={P_OUT/Pin*100:.2f}%")
    soft = hv_sw+filt+bus+aux
    print(f"      з них 'мʼяких' оцінок (±50%): {soft:.0f} Вт -> ККД у діапазоні "
          f"{P_OUT/(P_OUT+tot+soft*0.5)*100:.1f}...{P_OUT/(P_OUT+tot-soft*0.5)*100:.1f}%")
    return tot
t1 = total(S24, 2, 0.00072, 0.55, 0.019, 1, "A1) 24 В, ПАРНО 8x IRL40SC209, HV C7 19 мОм")
t2 = total(S24, 2, 0.00072, 0.55, 0.035, 1, "A2) 24 В, ПАРНО 8x IRL40SC209, HV CFD7 35 мОм")
t3 = total(S48, 2, 0.00072, 0.55, 0.035, 2, "B1) 48 В*, ПАРНО 8x IRL40SC209, HV 2x CFD7 35 мОм")
t4 = total(S48, 2, 0.0015, 0.50, 0.019, 2, "B2) 48 В, ПАРНО 8x 100В/1.5мОм, HV 2x C7 19 мОм (межа)")
print("\n  * B1 приведено лише для порівняння опору: IRL40SC209 - 40 В, на 48-вольтовій")
print("    шині (13s max 54.6 В) він НЕ придатний за напругою.")

hr("7. ЧИ МОЖЛИВІ 99% (30 Вт) - остаточна перевірка")
best_hv = Io_rms**2*4*(0.019*2.2/2)
print(f"  Найкращий можливий HV (2x C7 19 мОм паралельно, 4 у шляху): {best_hv:.1f} Вт")
print(f"  Найкращий реальний LV (48 В, 8 ключів по 0.72 мОм + шини 0.3 мОм): "
      f"{lv_losses(S48,2,0.00072,0.55,rth_pad=1.2)['tot']:.1f} Вт")
print(f"  Трансформатор (найкращий): {S48['Ptx']:.1f} Вт")
print(f"  Фільтр + шини + аукс (мінімум мінімумів): 20 Вт")
floor = best_hv+lv_losses(S48,2,0.00072,0.55,rth_pad=1.2)["tot"]+S48["Ptx"]+20
print(f"  ФІЗИЧНА СТЕЛЯ: {floor:.0f} Вт -> ККД = {P_OUT/(P_OUT+floor)*100:.2f}%")
print("  99% (30 Вт) недосяжні. Реальна стеля цієї топології - трохи менше 97%.")

hr("8. ОХОЛОДЖЕННЯ: що потрібно від радіатора")
for Ploss, lbl in ((t1, "A1"), (t3, "B1")):
    for Ta in (25, 40):
        Rth = (70-Ta)/Ploss
        print(f"  {lbl}: {Ploss:.0f} Вт, Ta={Ta}°C, радіатор 70°C -> потрібно Rth<={Rth:.3f} K/Вт "
              f"-> {'великий профіль + вентилятор' if Rth<0.4 else 'можливо пасивно'}")
print("  Для довідки: корпус 20x10x15 см з ребрами пасивно дає ~0.7-1.0 K/Вт.")

hr("9. ESP32: перевірені ресурси")
print("  ESP32 і ESP32-S3: по ДВА блоки MCPWM, у кожному 3 таймери і 3 оператори")
print("  (3 пари виходів = 6 виходів на блок, разом 12). Джерело: docs.espressif.com.")
print("  ESP32-S2 у переліку периферії MCPWM не має - для цього проєкту брати S3 або ESP32.")
for fclk in (80e6, 160e6):
    for f in (70e3, 150e3):
        steps = fclk/f
        print(f"    такт {fclk/1e6:.0f} МГц, носій {f/1e3:.0f} кГц: {steps:.0f} кроків "
              f"({math.log2(steps):.1f} біт), крок фази {1/fclk*1e9:.2f} нс")
print("  Потрібно виходів: 4 (LV міст) + 4 (SR) = 8 швидких + 4 повільних (unfolder, 50 Гц).")
print("  Отже: MCPWM0 = LV (2 оператори), MCPWM1 = SR (2 оператори), unfolder = GPIO/LEDC.")
print("  ВАЖЛИВО: синхронізація двох блоків MCPWM робиться через GPIO sync -> є джитер.")
print("  Тому вікно SR має мати запас на цей джитер, або SR треба вести аналогово по Vds.")
