# 1080p60 launcher default and build result

External capture now defaults to a 1920×1080 at 60 Hz EDID in commit
`062ce935cc36363c32d7d6b8a82adb99dca22cb9`. The EDID is valid, but the
FPGA build failed its timing checks. No new image was deployed and no
physical 1080p60 capture test was run. The local-loop fixture remains 1080p30.

The profile uses a 148.5 MHz pixel clock, totals 2200×1125, positive sync,
8-bit RGB and receiver `kClkRange=1`. The 128-byte EDID advertises only that
preferred detailed timing, with no established, standard or extension timings.
The independent `edid-decode --check` result is **EDID conformity: PASS**.
Its SHA256 is
`3eb2453cf0034be9bdd9242de9744eaf6eb4077c1c18c32c4dc12082204d09fe`.

Host validation passed 623 tests with one optional Migen-dependent simulation
skipped. The earlier launcher commit `0b97680` includes serial login, prepared
capture and GUI connection. The subsequent profile commit adds EDID timing,
receiver-range and artifact-mismatch coverage, with no silent VGA fallback.

The build used the immutable source export `artifacts/1080p60-source-001`,
pinned PYNQ 3.0.1 and Vivado/Vitis 2025.2. It reused the unchanged, hash-verified
1920×1080 capture RTL and provenance from the earlier generated gate because
its geometry and 142.857132 MHz AXI clock are identical. HLS was rebuilt and all
four stream-drain simulations passed. The original run and its first resume
were interrupted; the second resume preserved completed synthesis runs and
finished routing and bit generation under the one-off user service
`codex-pynq-1080p60-build-002`.

The strict publication check then rejected the candidate:

| Check | Result |
| --- | --- |
| Setup slack | +0.226 ns; no failing endpoints |
| Hold slack | +0.016 ns; no failing endpoints |
| Minimum-period slack | −0.320 ns; 14 failing endpoints |
| Deserializer clock | 742.5 MHz, `CLK_OUT_5x_hdmi_clk` |
| `ISERDESE2/CLK` minimum period | 1.667 ns required; 1.347 ns actual |
| Vivado diagnostic | `Timing 38-282`: timing requirements not met |

Passing setup and hold does not clear these minimum-period violations. The
checks were kept intact. A candidate bitstream exists in the implementation
run, but no paired deployment package was published. This result agrees with
PYNQ's documented [1080p electrical limitation on PYNQ-Z2](https://pynq.readthedocs.io/en/latest/pynq_overlays/pynqz2/pynqz2_base_overlay.html);
it does not establish whether an unqualified experimental image would work
with any particular HDMI source.

The board's previous VGA image was left in place. For the verified external
workflow, select `--external-mode vga`. The requested 1080p60 default remains
in source and requires a matching image; the launcher refuses an incompatible
VGA or 1080p30 image. Neither EDID validity nor host tests qualify 1080p60
capture on this hardware.

The [machine-readable result](1080p60-default.json) records the measurements
and local evidence paths. Raw timing, child-run diagnostics, independent EDID
decode and service results remain under `artifacts/1080p60-rx-001*`. User-saved
`capture.bmp`, `capture.json` and the unrelated recovery log were not committed.
