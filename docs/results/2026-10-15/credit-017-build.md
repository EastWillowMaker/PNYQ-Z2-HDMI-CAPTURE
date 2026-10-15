# Build017 passed CAD with a draining color pipeline

Isolated fresh HLS and Vivado implementation completed with exit0 at
2026-10-15 20:23:59 Asia/Taipei. Frozen build sources and SHA256 map are under
artifacts/m1-project-017-source. Gate RTL is unchanged from016; only the copied
color_convert pipeline pragma changes to style=flp. Both HLS cores were rebuilt.
Source commit34e35dd contains the fix and pre-CAD generated-RTL regression.

| Check | Result |
| --- | --- |
| Setup / hold worst slack | 0.401 /0.014ns |
| Bus skew | 56 MET,0violated |
| No-clock / unconstrained internal endpoints | 0 /0 |
| Missing external input/output delays | Retained5 /2 |
| CDC | 161CDC-3 info,4CDC-9 info,1retainedVTC CDC-6 warning;0critical |
| DRC | 8warnings,1advisory;0error/critical |
| Routed synchronizer attributes | 256Gray and6receiver-reset/data FFs ASYNC_REG |
| Generated HLS isolated drain | Four cases pass, byte-exact/boundaries/stalls |
| Actual exported HLS full VGA with stalls | Pass,307200pixels/230400words/480EOL |
| Ordinary local software suite | 308passed,1optional skip; no hosted CI |

The warnings and external delay gaps remain; this is not a warning-free or
complete external-I/O qualification. No timing/CDC/DRC gate or clock constraint
was relaxed. Main and all child run logs have no ERROR/CRITICAL WARNING. Existing
vendor XPM constraints/waivers remain; no broad waiver was added. Routed
post-review completed exit0 and checked ASYNC_REG attributes explicitly.

Artifact SHA256:

- Bit: dbcfa96f370ade0655e08c610903e34af08535649b8d9363be4ac590b00cdf1b
- HWH: 99563e23f95ca7dba525ca2132df2e8b75ce73e3e528fffebb86639549614b2e
- Gate: e4515603bf95855dc1aa82ecce4104bf22dfd05f9cce8d6d8d421887675dfbec
- Overlay archive: 15a5301661f5f67fbbff075d95e2af3729522a4a6c4bab967b3692d00061883c
- Unchanged v10 source archive: 8c716223f7928571a3704eb049e3827045c85168081f99b186b1009b24c298ae

Both archives and paired bit/HWH matched their hashes on the board at
/tmp/hdmi-capture-credit-017-v10. The first authorized smoke launch is recorded
in artifacts/operator/m1-017-v10-smoke-launch.log. CAD and HLS simulation do not
establish physical DMA completion, RGB exactness or M1 source accounting.

Reports and full CAD logs: artifacts/m1-project-017; generated-source comparison
and failing016 evidence: [drain report](credit-016-hls-drain.md). The original
vendor checkout, failed builds and real captures are preserved; no image upload.
