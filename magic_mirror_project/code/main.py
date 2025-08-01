import time
from machine import Pin, SPI
# from display import tft  # Suponha que tenha driver tft

while True:
    current_time = time.localtime()
    hour = current_time[3]
    minute = current_time[4]
    print(f"{hour:02}:{minute:02}")
    time.sleep(60)
