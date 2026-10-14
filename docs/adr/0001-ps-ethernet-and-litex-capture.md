# Use PS Ethernet with a LiteX capture subsystem

Accepted 2026-10-15 through user Q2. PYNQ-Z2's onboard PHY is wired to PS MIO,
so Linux on the PS owns Ethernet and sends complete raw RGB888 frames from PS
DDR. M0 reuses the existing PYNQ overlay to establish real HDMI capture; M1
inserts meaningful LiteX-generated capture control/statistics into the PL video
path and produces a reproducible image. Reusing the HDMI frontend and VDMA
avoids a new receiver and soft CPU, while preserving a completed-frame boundary
for later consumers. This incurs PS buffer/cache ownership and Vivado IP
integration work; the upstream LiteX board target alone does not supply it.
