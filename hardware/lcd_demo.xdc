# PYNQ-Z2 RPi header, confirmed by the low-speed LCD C wiring probe.
set_property -dict {PACKAGE_PIN W10 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports lcd_sck]
set_property -dict {PACKAGE_PIN V8 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports lcd_mosi]
set_property -dict {PACKAGE_PIN F19 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports lcd_cs]
set_property -dict {PACKAGE_PIN Y7 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports lcd_dc]
set_property -dict {PACKAGE_PIN F20 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports lcd_reset]
set_property -dict {PACKAGE_PIN W19 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports touch_cs]
set_property IOB TRUE [get_ports {lcd_sck lcd_mosi lcd_cs lcd_dc}]

# DIV=4 gives eight system-clock cycles per SPI period. The external timing
# budget is a demo assumption, not qualification of the LCD bridge's limits.
create_generated_clock -name lcd_spi_clock -source [get_pins -hier -filter {NAME =~ */lcd_demo_0/inst/clk}] -divide_by 8 [get_ports lcd_sck]
set_output_delay -clock lcd_spi_clock -max 5.0 [get_ports {lcd_mosi lcd_cs lcd_dc}]
set_output_delay -clock lcd_spi_clock -min 1.0 [get_ports {lcd_mosi lcd_cs lcd_dc}]
