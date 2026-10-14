"""Explicit half-second gate experiment; local board execution only."""
import argparse
import json
import time
from hdmi_capture.sources import LiteXSource
p=argparse.ArgumentParser()
p.add_argument('bitfile');p.add_argument('manifest')
a=p.parse_args()
s=LiteXSource(a.bitfile,a.manifest)
s.load_overlay(download=False)
report={'scope':'sequential GPIO snapshots; not per-DMA-frame association',
        'before':s.control.snapshot(sample_point='before_disable')}
try:
    s.control.enable(False)
    time.sleep(.5)
    report['disabled']=s.control.snapshot(sample_point='after_half_second_disabled')
finally:
    s.control.enable(True)
time.sleep(.5)
report['enabled']=s.control.snapshot(sample_point='after_half_second_enabled')
print(json.dumps(report,indent=2),flush=True)
