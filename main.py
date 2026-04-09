# ------------------------------ AI STETHOSCOPE ------------------------------
# This system monitors heart rate, temperature, and stress using:
# - MAX30102 (Heart rate & SpO2)
# - DS18B20 (Body temperature)
# - OLED Display (shows health summary)
# - Stress is calculated using HRV (SDNN and RMSSD)
# ---------------------------------------------------------------------------

from machine import Pin, I2C, ADC
import ssd1306
import utime, math
from max30102 import MAX30102
from ds18x20 import DS18X20
from onewire import OneWire

# -------------------- I2C & Sensor Setup --------------------

# OLED connected to I2C1: SDA=GP6, SCL=GP7
i2c_oled = I2C(1, scl=Pin(7), sda=Pin(6))
oled = ssd1306.SSD1306_I2C(128, 64, i2c_oled)

# MAX30102 connected to I2C0: SDA=GP4, SCL=GP5
i2c_max = I2C(0, scl=Pin(5), sda=Pin(4))
max30102 = MAX30102(i2c_max)

# DS18B20 temperature sensor on GPIO15
ds_sensor = DS18X20(OneWire(Pin(15)))
roms = ds_sensor.scan()

# Battery voltage monitoring using ADC on GP26
adc_battery = ADC(Pin(26))

# -------------------- Utility Functions --------------------

# Display 3 lines of text on the OLED
def show_on_oled(line1="", line2="", line3=""):
    oled.fill(0)
    oled.text(line1, 0, 0)
    oled.text(line2, 0, 10)
    oled.text(line3, 0, 20)
    oled.show()

# Read and return battery voltage
def read_battery_voltage():
    raw_value = adc_battery.read_u16()
    voltage = (raw_value / 65535) * 3.3
    return voltage

# Draw a simple battery icon (used when charging)
def show_charging_icon():
    oled.fill_rect(110, 10, 10, 10, 1)
    oled.fill_rect(115, 15, 5, 5, 0)
    oled.show()

# Calculate SDNN from RR intervals
def calculate_sdnn(rr):
    if len(rr) < 2:
        return 0
    mean_rr = sum(rr) / len(rr)
    variance = sum((x - mean_rr) ** 2 for x in rr) / (len(rr) - 1)
    return math.sqrt(variance)

# Calculate RMSSD from RR intervals
def calculate_rmssd(rr):
    if len(rr) < 2:
        return 0
    diff_sq = [(rr[i] - rr[i - 1]) ** 2 for i in range(1, len(rr))]
    return math.sqrt(sum(diff_sq) / len(diff_sq))

# Classify stress based on SDNN and RMSSD thresholds
def classify_stress(sdnn, rmssd):
    if sdnn > 50 and rmssd > 42:
        return "Low stress"
    elif 20 < sdnn <= 50 and 20 < rmssd <= 42:
        return "Medium stress"
    else:
        return "High stress"

# -------------------- Data Collection Phase --------------------

bpm_list = []
rr_intervals = []
samples = []

prev_ir = 0
last_beat_time = utime.ticks_ms()
sample_count = 0

print("Starting 40-sample data collection...")

# Show a fixed message while collecting samples
show_on_oled("Please Wait...", "Collecting data", "Calculating...")

# Collect 40 valid BPM + RR interval samples
while sample_count < 40:
    max30102.read()
    ir = max30102.ir

    # Skip if reading too low (finger not placed)
    if ir < 10000:
        continue

    # Detect peak and calculate BPM from RR interval
    if ir > prev_ir and prev_ir < 50000:
        now = utime.ticks_ms()
        rr = utime.ticks_diff(now, last_beat_time)
        if 300 < rr < 2000:  # Valid human RR range (300ms to 2000ms)
            bpm = 60000 / rr
            bpm_list.append(bpm)
            rr_intervals.append(rr)
            samples.append({'bpm': bpm, 'rr': rr})
            sample_count += 1
            print(f"Sample {sample_count}: BPM={bpm:.1f}, RR={rr} ms")
            last_beat_time = now
    prev_ir = ir
    utime.sleep_ms(30)

# -------------------- Post Processing --------------------

# Read temperature if sensor is connected
if roms:
    ds_sensor.convert_temp()
    utime.sleep_ms(750)
    temperature = ds_sensor.read_temp(roms[0])
else:
    temperature = None
    print("No DS18B20 sensor detected.")

# Calculate average BPM, SDNN, RMSSD
avg_bpm = sum(bpm_list) / len(bpm_list)
sdnn = calculate_sdnn(rr_intervals)
rmssd = calculate_rmssd(rr_intervals)
stress_level = classify_stress(sdnn, rmssd)

# Choose best BPM sample (closest to average)
best_sample = min(samples, key=lambda x: abs(x['bpm'] - avg_bpm))
best_bpm = best_sample['bpm']
best_rr = best_sample['rr']

# Get battery voltage and status
battery_voltage = read_battery_voltage()
charging_status = "Charging" if battery_voltage < 3.7 else "Full"

# -------------------- OLED Final Display --------------------

oled.fill(0)

# Centered title
oled.text("AI STETHOSCOPE", 12, 0)

# Vital signs display
oled.text(f"BPM : {int(best_bpm)}", 0, 15)
oled.text(f"TEMP: {temperature:.1f} C" if temperature else "TEMP: N/A", 0, 25)
oled.text(f"STRS: {stress_level}", 0, 35)

# Battery display with icon
oled.text(f"BAT : {battery_voltage:.2f}V", 0, 50)
if charging_status == "Charging":
    # Charging icon: outline box with arrow inside
    oled.rect(100, 48, 20, 10, 1)  # battery shape
    oled.line(108, 50, 112, 54, 1)  # arrow down
    oled.line(112, 50, 108, 54, 1)  # arrow up
else:
    # Full battery icon: filled box
    oled.fill_rect(100, 48, 20, 10, 1)

oled.show()

# -------------------- Wait then Clear OLED --------------------

# Wait 30 seconds before clearing display
utime.sleep(30)
oled.fill(0)
oled.show()
