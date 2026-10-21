"""Slow, standalone Waveshare LCD C wiring diagnostic for PYNQ-Z2.

This bring-up probe uses the base overlay's MicroBlaze GPIO, not the proposed
video gateware. LCD writes need visual confirmation; optional SPI reads target
the separate touch ADC because the LCD has no header readback path.
"""

import argparse
import json
import signal
import time


# Waveshare35c.dtbo init sequence, with landscape MADCTL and RGB565.
INIT = [
    (0xF1, [0x36, 0x04, 0x00, 0x3C, 0x0F, 0x8F]),
    (0xF2, [0x18, 0xA3, 0x12, 0x02, 0xB2, 0x12, 0xFF, 0x10, 0x00]),
    (0xF8, [0x21, 0x04]), (0xF9, [0x00, 0x08]),
    (0x36, [0x08]), (0xB4, [0x00]), (0xC1, [0x41]),
    (0xC5, [0x00, 0x91, 0x80, 0x00]),
    (0xE0, [0x0F, 0x1F, 0x1C, 0x0C, 0x0F, 0x08, 0x48, 0x98,
            0x37, 0x0A, 0x13, 0x04, 0x11, 0x0D, 0x00]),
    (0xE1, [0x0F, 0x32, 0x2E, 0x0B, 0x0D, 0x05, 0x47, 0x75,
            0x37, 0x06, 0x10, 0x03, 0x24, 0x20, 0x00]),
    (0x3A, [0x55]), (0x11, []), (0x36, [0x28]),
]

PROGRAM = r"""
#include <gpio.h>
#include <timer.h>

static gpio clk, mosi, miso, lcd_cs, touch_cs, dc, rst, pen;

static unsigned int exchange(unsigned int value, unsigned int bits) {
    unsigned int received = 0;
    for (unsigned int i = bits; i > 0; --i) {
        gpio_write(mosi, (value >> (i - 1)) & 1);
        delay_us(2);
        gpio_write(clk, 1);
        delay_us(2);
        received = (received << 1) | gpio_read(miso);
        gpio_write(clk, 0);
    }
    return received;
}

static void output(gpio pin, unsigned int value) {
    gpio_write(pin, value);
    gpio_set_direction(pin, GPIO_OUT);
}

int setup_pins(void) {
    /* Base-overlay IOP indices equal BCM GPIO numbers, not header positions. */
    lcd_cs = gpio_open(8); touch_cs = gpio_open(7);
    clk = gpio_open(11); mosi = gpio_open(10); miso = gpio_open(9);
    dc = gpio_open(24); rst = gpio_open(25); pen = gpio_open(17);
    gpio_set_direction(miso, GPIO_IN);
    gpio_set_direction(pen, GPIO_IN);
    output(lcd_cs, 1); output(touch_cs, 1);
    output(clk, 0); output(mosi, 0); output(dc, 1); output(rst, 1);
    delay_ms(10);
    gpio_write(rst, 0); delay_ms(20);
    gpio_write(rst, 1); delay_ms(150);
    return 0;
}

int lcd_word(unsigned int data_mode, unsigned int value) {
    gpio_write(dc, data_mode != 0);
    gpio_write(lcd_cs, 0);
    /* The module bridge requires 16 clocks for commands and parameters too. */
    exchange(value & 0xffff, 16);
    gpio_write(lcd_cs, 1);
    return 0;
}

int draw_row(unsigned int y) {
    static const unsigned int colors[8] = {
        0xf800, 0x07e0, 0x001f, 0xffff, 0x0000, 0xffe0, 0x07ff, 0xf81f
    };
    if (y >= 320) return -1;
    gpio_write(dc, 1);
    gpio_write(lcd_cs, 0);
    for (unsigned int x = 0; x < 480; ++x) {
        unsigned int pixel = colors[x / 60];
        if (x < 3 || x >= 477 || y < 3 || y >= 317) pixel = 0xffff;
        if (x >= 8 && x < 32 && y >= 8 && y < 32) pixel = 0xffff;
        exchange(pixel, 16);
    }
    gpio_write(lcd_cs, 1);
    return 480;
}

int touch_read(unsigned int command) {
    unsigned int raw;
    gpio_write(lcd_cs, 1);
    gpio_write(touch_cs, 0);
    exchange(command & 0xff, 8);
    raw = exchange(0, 16);
    gpio_write(touch_cs, 1);
    return (raw >> 3) & 0xfff;
}

int pen_level(void) { return gpio_read(pen); }

int idle_pins(void) {
    gpio_write(lcd_cs, 1); gpio_write(touch_cs, 1);
    gpio_write(clk, 0); gpio_write(mosi, 0);
    gpio_write(dc, 1); gpio_write(rst, 1);
    return 0;
}
"""


def command(rpc, value, data=()):
    rpc.lcd_word(0, value)
    for byte in data:
        rpc.lcd_word(1, byte)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-base", action="store_true",
                        help="replace the active FPGA design with base.bit")
    parser.add_argument("--read-touch", action="store_true",
                        help="sample the separate touch ADC to exercise SPI MISO")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=180,
                        help="whole-probe timeout in seconds")
    args = parser.parse_args()
    if not args.load_base:
        parser.error("--load-base is required; stop capture and other FPGA users first")
    if not 1 <= args.samples <= 120 or not 30 <= args.timeout <= 600:
        parser.error("samples must be 1..120 and timeout must be 30..600")

    def timed_out(signum, frame):
        raise TimeoutError("SPI diagnostic exceeded its time limit")

    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(args.timeout)
    from pynq.overlays.base import BaseOverlay
    from pynq.lib.pynqmicroblaze import MicroblazeRPC

    print("Loading base.bit; this is a slow wiring probe, not a video benchmark.",
          flush=True)
    base = BaseOverlay("base.bit")
    base.select_rpi()
    rpc = MicroblazeRPC(base.iop_rpi, PROGRAM)
    completed = False
    try:
        rpc.setup_pins()
        for opcode, data in INIT:
            command(rpc, opcode, data)
        time.sleep(0.255)
        command(rpc, 0x29)
        time.sleep(0.1)
        command(rpc, 0x2A, [0, 0, 1, 0xDF])
        command(rpc, 0x2B, [0, 0, 1, 0x3F])
        command(rpc, 0x2C)
        start = time.monotonic()
        for row in range(320):
            if rpc.draw_row(row) != 480:
                raise RuntimeError("MicroBlaze did not complete the requested row")
            if row % 80 == 79:
                print(json.dumps({"rows_written": row + 1}), flush=True)
        print(json.dumps({"write_status": "transmitted_not_visually_verified",
                          "pixels": 153600,
                          "elapsed_seconds": time.monotonic() - start,
                          "lcd_readback": "not_available_on_header"}), flush=True)
        print("Expect eight bars: red, green, blue, white, black, yellow, cyan, "
              "magenta; white border and a white square near the top-left.", flush=True)
        if args.read_touch:
            print("Touch ADC samples follow. Press different screen locations to "
                  "check response; these are not LCD register reads.", flush=True)
            for sample in range(args.samples):
                # Differential 12-bit conversions; power down between samples.
                x = rpc.touch_read(0xD0)
                y = rpc.touch_read(0x90)
                print(json.dumps({"sample": sample, "x": x, "y": y,
                                  "pen_n": rpc.pen_level(),
                                  "read_status": "raw_unverified"}), flush=True)
                time.sleep(0.5)
        rpc.idle_pins()
        completed = True
    finally:
        # A stalled RPC cannot safely be used for a second cleanup RPC.
        rpc.reset()
        signal.alarm(0)
        if not completed:
            print("Probe aborted; MicroBlaze reset. Pin idle state is unverified.",
                  flush=True)


if __name__ == "__main__":
    main()
