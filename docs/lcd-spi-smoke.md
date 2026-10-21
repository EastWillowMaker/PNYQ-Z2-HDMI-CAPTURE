# LCD SPI wiring probe

Run [the probe](../tools/lcd_spi_smoke.py) on a PYNQ-Z2 with PYNQ 3.0.1 and a
Waveshare 3.5inch RPi LCD (C) on its Raspberry Pi header. The user confirmed
the header mapping on 2026-10-22. This is a standalone bring-up experiment,
not the HDMI preview implementation or a high-speed SPI qualification.

Stop capture and other FPGA users first. `--load-base` replaces the active FPGA
design and its RPi MicroBlaze program. The base overlay and RPi shared-pin
selection remain active afterward; the probe does not restart capture or restore
the previous overlay. In particular, shared pins are not returned to Pmod A.

```sh
sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python -u \
    tools/lcd_spi_smoke.py --load-base
```

The probe compiles a small MicroBlaze GPIO program through PYNQ's existing RPC
support. It sends SPI mode 0, MSB first, with at least 2 microseconds per half
cycle plus software overhead. This bounds the nominal clock below 250 kHz;
the actual clock has not been measured. It uses no new bitstream or installation.
The stock base overlay is intentionally separate from the eventual hardware
scaler and SPI engine.

Expected display: eight vertical bars, red, green, blue, white, black, yellow,
cyan and magenta; a white border; and a white square near the top-left corner.
A completed program only establishes that the MicroBlaze completed its write
loop. A person must confirm the visible pattern and colors. The probe leaves
the pattern displayed. Successful cleanup deselects both devices, idles the
clock low, then resets the MicroBlaze. An abort resets the MicroBlaze but cannot
guarantee idle pin levels; it explicitly reports that limit.

## Read-path limitation

The module exposes touch-controller MISO, not an LCD register/framebuffer
readback connection. Do not interpret all-zero, all-one, or arbitrary received
bytes as an LCD identity or a successful write/read comparison.

To exercise the separate touch ADC's SPI read path:

```sh
sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python -u tools/lcd_spi_smoke.py \
    --load-base --read-touch --samples 60
```

After drawing, this records raw 12-bit X/Y conversions and the active-low pen
signal at half-second intervals. Press different screen locations to look for
correlated coordinate changes and pen transitions. Raw samples alone do not
prove a working read path, and this is not touch calibration or a touch feature
for the HDMI preview. LCD CS stays high during touch transactions, and touch CS
stays high during LCD transactions.

| Signal | Header pin | Base-overlay IOP index / BCM GPIO |
| --- | --- | --- |
| LCD CS | 24 | 8 |
| MOSI | 19 | 10 |
| SCK | 23 | 11 |
| D/C | 18 | 24 |
| Reset | 22 | 25 |
| Touch CS | 26 | 7 |
| Touch MISO | 21 | 9 |
| Touch IRQ | 11 | 17 |

Commands and their eight-bit parameters occupy 16 wire bits each because this
LCD module uses an SPI-to-parallel bridge. RGB565 pixels also occupy 16 wire
bits. The initialization values come from the manufacturer's LCD C overlay.

References:

- [Waveshare LCD C pinout and driver downloads](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_%28C%29)
- [Manufacturer Waveshare35c overlay ZIP](https://files.waveshare.com/wiki/common/Waveshare35c.zip)
- [PYNQ 3.0.1 header mapping](https://github.com/Xilinx/PYNQ/blob/v3.0.1/boards/Pynq-Z2/base/constants.py)
- [PYNQ 3.0.1 MicroBlaze RPC](https://github.com/Xilinx/PYNQ/blob/v3.0.1/pynq/lib/pynqmicroblaze/rpc.py)
- [Linux module bridge protocol](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/tiny/ili9486.c)

## Board result (2026-10-22)

The user confirmed that the complete pattern and colors looked correct. The
board run completed all 153,600 pixel writes and exited zero after idle-pin
cleanup and MicroBlaze reset. Drawing took 58.806 seconds with this deliberately
slow GPIO implementation; this is not the planned SPI engine's performance.
Python compilation, CLI help and the embedded C syntax check passed locally.

The optional read test returned 20 identical idle samples: X=0, Y=4095,
PEN_N=1. No controlled screen press was recorded, so these samples do not
qualify touch read functionality. LCD readback is unavailable on this header.
High-speed SPI, live HDMI scaling, 30 fps, optical latency, automatic recovery
and concurrent PC capture remain unverified.

The [first run](results/2026-10-22/lcd-spi-run-001.log) failed before overlay
loading because sudo dropped `XILINX_XRT`. The
[second run](results/2026-10-22/lcd-spi-run-002.log) used the documented
`XILINX_XRT=/usr` environment and completed. Local and board program SHA256:
`701fd578b8ca18896d55b8da40ac95cd6c6c84b660dfba374cd13a2a71313f0c`.
