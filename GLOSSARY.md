# HDMI Capture

Terms for acquiring complete video frames from the PYNQ-Z2 HDMI input.

## Language

**Source frame**:
A single complete image in the incoming HDMI video sequence.
_Avoid_: Packet, screenshot

**Delivered frame**:
A complete source frame received by the PC capture client, with its metadata.
_Avoid_: Preview frame

**LCD preview**:
A local view of the HDMI input that preserves the complete image and its aspect
ratio. It may skip source frames to keep the displayed picture current.

**LCD update rate**:
The number of new source images displayed on the LCD per second, distinct from
the HDMI input refresh rate and the PC delivered frame rate.

**Input refresh rate**:
The number of source frames presented by the HDMI source per second.

**Delivered frame rate**:
The number of complete new source frames delivered to the PC per second.

**Output loopback**:
A test in which the board's HDMI output supplies a known image sequence to
the same board's HDMI input through a physical cable.
_Avoid_: Active bypass

**RGB888**:
A pixel representation with three eight-bit channels ordered red, green, blue.
_Avoid_: RGB444 packed

**RGB565 preview**:
The LCD preview's color representation, with five red, six green and five blue
bits per pixel. It does not change the RGB888 representation delivered to the PC.

**Intentional sampling**:
Deliberate selection of some complete source frames for capture.

**Overrun**:
Loss of capture data because the capture path cannot accept or retain it.

**Baseline capture**:
Real HDMI capture used to establish initial functionality before LiteX integration.

**Formal LiteX capture**:
Real HDMI capture in which LiteX-generated logic participates in acquisition.

**Prepared receiver**:
A receiver ready for a source to establish its HDMI signal, with capture stopped.
Preparation alone does not establish a valid input mode or a captured frame.

**Preparation receipt**:
A record of the receiver's prepared configuration within the current board boot.
It is not an independent hardware identity or a unique capture epoch.

**Credit lease**:
Exclusive ownership of one completed capture whose pixels and source identity
remain stable until the consumer releases it.

**Fail-stop**:
Ending acquisition and reporting an input or integrity fault instead of
continuing to deliver frames.

**Safe shutdown**:
A stopped capture whose hardware cannot write into memory released by its owner.
