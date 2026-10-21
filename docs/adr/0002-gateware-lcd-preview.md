# Process the LCD preview in gateware

The earlier M4 proposal began with software scaling. The user now requires
gateware to scale HDMI input images and transmit them over SPI to the Waveshare
3.5inch RPi LCD (C). Software may initialize the LCD and configure capture, but
must not convert pixels or transfer each frame over SPI. This moves development
and resource costs into the FPGA design to meet the requested hardware data path.

The LCD is a freshness-oriented preview and may skip source frames independently
of PC capture. Both outputs must work simultaneously while preserving the PC
capture contract. The preview must retain the entire source image and its aspect
ratio. On input-resolution changes, select 0 or 90 degrees to minimize black
borders, retaining the current orientation on ties. A fixed physical mounting
may consequently show a sideways image.

Initial qualification covers existing VGA and 1080p progressive modes at their
verified timings. Occasional LCD scanout tearing is accepted if needed for
freshness, but each transmitted image must come from one complete source frame.
The user accepted RGB565 for the LCD, with RGB888 unchanged for PC capture.
The low-speed wiring probe passed with user-confirmed correct colors and geometry;
high-speed electrical timing remains unverified. Buffer ownership and the new
gateware interfaces are proposed in the
[full design](../superpowers/specs/2026-10-22-lcd-preview-design.md).

The accepted initial target is 30 new displayed frames per second and at most
100 ms source-to-visible latency, subject to hardware feasibility checks. These
are design targets, not measured results or a guarantee based on the advertised
SPI clock. No LCD implementation or hardware qualification is established by
this decision.

Source: user design interview, 2026-10-21. See the
[LCD requirements](../requirements.md#lcd-preview-design-interview-2026-10-21).
