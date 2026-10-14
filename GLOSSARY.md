# HDMI Capture

Terms for acquiring complete video frames from the PYNQ-Z2 HDMI input.

## Language

**Source frame**:
A single complete image in the incoming HDMI video sequence.
_Avoid_: Packet, screenshot

**Delivered frame**:
A complete source frame received by the PC capture client, with its metadata.
_Avoid_: Preview frame

**Input refresh rate**:
The number of source frames presented by the HDMI source per second.

**Delivered frame rate**:
The number of complete new source frames delivered to the PC per second.

**RGB888**:
A pixel representation with three eight-bit channels ordered red, green, blue.
_Avoid_: RGB444 packed

**Intentional sampling**:
Deliberate selection of some complete source frames for capture.

**Overrun**:
Loss of capture data because the capture path cannot accept or retain it.

**Baseline capture**:
Real HDMI capture used to establish initial functionality before LiteX integration.

**Formal LiteX capture**:
Real HDMI capture in which LiteX-generated logic participates in acquisition.
