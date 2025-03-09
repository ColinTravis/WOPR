from machine import Pin, SPI, RTC
import network
import max7219
import random
from time import sleep
import ntptime
import socket
import json
import time
import select
import os

class Config:
    def __init__(self):
        self.start_hour = 7
        self.end_hour = 1
        self.enabled = True
        self.timezone = -5  # Chicago CDT timezone
        self.wifi_ssid = 'SSID'  # Default SSID
        self.wifi_pass = 'PASS'  # Default password
        try:
            with open('config.json', 'r') as f:
                data = json.load(f)
                self.__dict__.update(data)
        except:
            self.save()

    def save(self):
        with open('config.json', 'w') as f:
            json.dump(self.__dict__, f)

config = Config()

# Initialize WiFi with config values
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
network.hostname('WOPR')
wlan.connect(config.wifi_ssid, config.wifi_pass)

# Wait for connect or fail
max_wait = 10
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    print('waiting for connection...')
    time.sleep(1)

# Handle connection error
if wlan.status() != 3:
    raise RuntimeError('network connection failed')
else:
    print('connected')
    status = wlan.ifconfig()
    print('ip = ' + status[0])

    # Add retry logic for NTP sync
    def sync_ntp():
        retry_count = 3
        while retry_count > 0:
            try:
                ntptime.settime()
                print('NTP sync successful')
                return True
            except OSError as e:
                print(f'NTP sync failed (attempts left: {retry_count-1}): {e}')
                retry_count -= 1
                time.sleep(1)
        return False

    if not sync_ntp():
        print('Warning: Could not sync time with NTP server')

# Initialize display
spi = SPI(0,sck=Pin(2),mosi=Pin(3))
cs = Pin(5, Pin.OUT)
display = max7219.Matrix8x8(spi, cs, 12)
display.brightness(0)

def get_local_time():
    rtc = RTC()
    dt = rtc.datetime()
    hour = (dt[4] + config.timezone) % 24
    return hour, dt[5], dt[6]

def serve_webpage():
    hour, minute, second = get_local_time()
    current_time = "{:02d}:{:02d}:{:02d}".format(hour, minute, second)
    html = """<!DOCTYPE html>
<html><head><title>LED Display Control</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:Arial;margin:20px;}
.btn{padding:10px;margin:5px;}</style></head>
<body>
<h1>LED Display Control</h1>
<p>Current Time: %s</p>
<form action="/update" method="get">
Start Hour (0-23): <input type="number" name="start" value="%d" min="0" max="23"><br>
End Hour (0-23): <input type="number" name="end" value="%d" min="0" max="23"><br>
Timezone (UTC): <select name="tz">
%s
</select><br>
<input type="submit" value="Update Settings" class="btn">
</form>
<a href="/on"><button class="btn">Turn On</button></a>
<a href="/off"><button class="btn">Turn Off</button></a>
<p>Current Status: %s</p>
</body></html>
""" % (
    current_time,
    config.start_hour,
    config.end_hour,
    ''.join(f'<option value="{i}"{" selected" if i == config.timezone else ""}>UTC{i:+d}</option>' for i in range(-12, 15)),
    "On" if config.enabled else "Off"
)
    return html

def handle_request(client):
    try:
        req = client.recv(1024).decode('utf-8').split('\r\n')[0]
        print(f"Request: {req}")  # Debug print

        if '/update' in req:
            params = req.split('?')[1].split(' ')[0]
            for param in params.split('&'):
                if 'start=' in param:
                    config.start_hour = int(param.split('=')[1])
                elif 'end=' in param:
                    config.end_hour = int(param.split('=')[1])
                elif 'tz=' in param:
                    config.timezone = int(param.split('=')[1])
            config.save()
            print(f"Updated config: {config.__dict__}")  # Debug print
        elif '/on' in req:
            config.enabled = True
            config.save()
            print("Display enabled")  # Debug print
        elif '/off' in req:
            config.enabled = False
            config.save()
            clear_display()
            print("Display disabled")  # Debug print
    except Exception as e:
        print(f"Error handling request: {e}")  # Debug print

    client.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
    client.send(serve_webpage())
    client.close()

def start_server():
    s = socket.socket()
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s.bind(addr)
    s.listen(1)
    return s

def is_display_time():
    hour = get_local_time()[0]
    if config.start_hour < config.end_hour:
        return config.start_hour <= hour < config.end_hour
    else:
        return hour >= config.start_hour or hour < config.end_hour

def clear_display():
    for y in range(8):
        for x in range(96):
            display.pixel(x, y, 0)
    display.show()
    sleep(0.1)  # Small delay to ensure display updates

def update_display_pattern():
    for y in range(8):
        for x in range(96):
            flip = random.randint(0, 1)
            if flip == 0:
                flipp = random.randint(0, 1)
                display.pixel(x,y,1 if flipp == 0 else 0)
    display.show()

server_socket = start_server()
print('Web server started on port 80')

while True:
    # Handle web requests
    try:
        r, w, err = select.select([server_socket], [], [], 0.1)
        if r:
            for readable in r:
                client, addr = readable.accept()
                handle_request(client)
    except Exception as e:
        print(f"Error in web handling: {e}")

    # Handle display updates
    if config.enabled and is_display_time():
        try:
            update_display_pattern()
            timeflip = random.randint(0,3)
            sleep([0.5, 1, 1.5, 2][timeflip])
        except Exception as e:
            print(f"Error updating display: {e}")
    else:
        try:
            clear_display()
            sleep(1)
        except Exception as e:
            print(f"Error clearing display: {e}")
