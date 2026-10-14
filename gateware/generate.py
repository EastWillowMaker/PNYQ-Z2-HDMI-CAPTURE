"""Run: python -m gateware.generate --output artifacts/litex_capture.v"""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path

from migen import ClockDomain
from migen.fhdl import verilog

from .capture import VideoCapture


def verify_dependencies():
    """Reject drift from the exact source packages used for simulation."""
    dependencies = json.loads(Path(__file__).with_name("dependencies.json").read_text())
    for name, expected in dependencies.items():
        root = Path(importlib.import_module(name).__file__).parent
        digest = hashlib.sha256()
        for source in sorted(root.rglob("*.py")):
            digest.update(str(source.relative_to(root)).encode() + b"\0" +
                          source.read_bytes() + b"\0")
        if (importlib.metadata.version(name) != expected["version"] or
                digest.hexdigest() != expected["installed_python_sha256"]):
            raise RuntimeError(f"{name} differs from gateware/dependencies.json")
    return dependencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/litex_capture.v"))
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--clock-hz", type=int, default=142857132)
    args = parser.parse_args()
    dependencies = verify_dependencies()
    module = VideoCapture(args.width, args.height)
    module.clock_domains.cd_sys = ClockDomain("sys")
    module.cd_sys.clk.attr.add(("X_INTERFACE_INFO", "xilinx.com:signal:clock:1.0 sys_clk CLK"))
    module.cd_sys.clk.attr.add(("X_INTERFACE_PARAMETER",
                               "ASSOCIATED_BUSIF s_axis:m_axis, ASSOCIATED_RESET sys_rst, "
                               f"FREQ_HZ {args.clock_hz}"))
    module.cd_sys.rst.attr.add(("X_INTERFACE_INFO", "xilinx.com:signal:reset:1.0 sys_rst RST"))
    module.cd_sys.rst.attr.add(("X_INTERFACE_PARAMETER", "POLARITY ACTIVE_HIGH"))
    # Explicit names prevent conversion's inferred names from being an ABI.
    for prefix, endpoint in (("s_axis", module.sink), ("m_axis", module.source)):
        for field, suffix in (("data", "tdata"), ("valid", "tvalid"),
                              ("ready", "tready"), ("first", "tuser"),
                              ("last", "tlast")):
            getattr(endpoint, field).name_override = prefix + "_" + suffix
    for signal in module.ports():
        if id(signal) not in {id(s) for s in (module.sink.data, module.sink.valid, module.sink.ready,
                          module.sink.first, module.sink.last, module.source.data,
                          module.source.valid, module.source.ready,
                          module.source.first, module.source.last)}:
            # Signals other than counters were assigned inferred class names.
            for name, value in vars(module).items():
                if value is signal:
                    signal.name_override = name
                    break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = str(verilog.convert(module, ios=module.ports() | {module.cd_sys.clk, module.cd_sys.rst},
                               name="litex_capture"))
    args.output.write_text(text)
    metadata = {"width": args.width, "height": args.height, "clock_hz": args.clock_hz,
                "rtl_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "source_sha256": hashlib.sha256(Path(__file__).with_name("capture.py").read_bytes()).hexdigest(),
                "dependencies": dependencies}
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
