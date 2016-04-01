# import time
import sys
sys.path.append('lib')

import utime
import math
import gc

from uasyncio import core
from trezor import ui

from .import utils

if __debug__:
    import logging
    logging.basicConfig(level=logging.INFO)

loop = core.get_event_loop()

def perf_info():
    mem_free = gc.mem_free()
    # gc.collect()
    print("free_mem: %s/%s, last_sleep: %.06f" % \
          (mem_free, gc.mem_free(), loop.last_sleep))
    loop.call_later(1, perf_info)

def animate():
    col = 0
    # hawcons gesture
    f = open('playground/tap_64.toi', 'r')

    while True:
        col %= 0xff
        col += 0x0f

        ui.display.icon(170, 170, f.read(), 0xffff, utils.rgb2color(col, 0, 0))
        # ui.display.icon(100, 100, f.read(), 0xffff, utils.rgb2color(col, 0, 0))
        f.seek(0)

        yield core.Sleep(0.5)

sec = 0
event = None
def sekunda(x):
    global sec
    print('Sekunda %d' % sec)
    

    if sec == 0:
        # if loop.button_cb:
        #    loop.call_soon(loop.button_cb, 'levy')
        #    loop.button_cb = None
        return

    sec += 1
    loop.call_later(1, sekunda, x)

def wait_for():
    print("Jsem tady")

    ktery = yield core.IOButton()
    print(ktery)
    
    print("Po cekani na event")

def tap_to_confirm():
    STEP_X = 0.07
    DELAY = 0.01
    BASE_COLOR = (0x00, 0x00, 0x00)
    MIN_COLOR = 0x00
    MAX_COLOR = 0xB0

    _background = utils.rgb2color(255, 255, 255)

    f = open('playground/tap_64.toi', 'r')

    x = math.pi
    while True:
        x += STEP_X
        if x > 2 * math.pi:
            x -= 2 * math.pi
        y = 1 + math.sin(x)
        
        # ui.display.bar(0, 170, 240, 70, _background)

        # Normalize color from interval 0:2 to MIN_COLOR:MAX_COLOR
        col = int((MAX_COLOR - MIN_COLOR) / 2 * y) + MIN_COLOR
        foreground = utils.rgb2color(BASE_COLOR[0] + col, BASE_COLOR[1] + col, BASE_COLOR[2] + col)

        ui.display.text(68, 212, 'TAP TO CONFIRM', 2, foreground, _background)

        f.seek(0)
        ui.display.icon(3, 170, f.read(), _background, foreground)
        # ui.display.icon(165, 50, f.read(), _background, foreground)


        yield core.Sleep(DELAY)

def run():
    # sekunda(3)
    # loop.call_soon(wait_for())

    loop.call_soon(perf_info)
    loop.call_soon(tap_to_confirm())
    # loop.call_soon(animate())

    loop.run_forever()
    loop.close()