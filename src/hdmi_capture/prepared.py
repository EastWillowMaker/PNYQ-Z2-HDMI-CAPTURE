"""Prepare and attach a receiver under exclusive PYNQ configuration ownership."""

import hashlib
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time

from .sources import CREDIT_ABI, DMA_ERRORS, LiteXSource, SourceError, verify_litex_artifacts


def wait_ready_file(path, timeout=120, *, clock=time.monotonic, sleep=time.sleep):
    """Wait for a new regular marker without accessing receiver hardware."""
    if not math.isfinite(timeout) or not 0 < timeout <= 900:
        raise ValueError("Ready timeout must be finite and in (0, 900]")
    path = Path(path)
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise SourceError("Ready marker must be absent before waiting")
    deadline = clock() + timeout
    while clock() < deadline:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            sleep(min(0.1, max(0, deadline - clock())))
            continue
        if not stat.S_ISREG(mode):
            raise SourceError("Ready marker must arrive as a regular file")
        return
    raise SourceError("Timed out waiting for source readiness marker")


def _boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def _fpga_state():
    return Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()


def _raw_state():
    from pynq.pl_server.global_state import STATE_DIR
    # GlobalState.__init__ recomputes the saved hash from today's file bytes.
    return json.loads((Path(STATE_DIR) / "global_pl_state.json").read_text())


def _check_sdk_shutdown():
    try:
        state = _raw_state()
    except FileNotFoundError:
        return
    except (OSError, ValueError) as error:
        raise SourceError(f"Cannot check PYNQ shutdown state: {error}") from error
    # PYNQ download invokes these old register maps before programming.
    if not isinstance(state, dict) or state.get("shutdown_ips"):
        raise SourceError("PYNQ shutdown IP state requires separate verified recovery before preparation")


def _artifacts(source):
    record = verify_litex_artifacts(source.bitfile, source.manifest_path)
    if record.get("capture_interface") != CREDIT_ABI or "source_health_sha256" not in record:
        raise SourceError("Prepared capture requires the single-credit artifact")
    bitfile = Path(source.bitfile).resolve()
    paths = dict(bitfile=bitfile, hwh=bitfile.with_suffix(".hwh"),
                 manifest=Path(source.manifest_path).resolve())
    return {name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            for name, path in paths.items()}


def _state_identity(artifacts):
    state = _raw_state()
    keys = ("bitfile_name", "bitfile_hash", "timestamp", "active_name")
    if any(not isinstance(state.get(key), str) or not state[key] for key in keys):
        raise SourceError("PYNQ loaded-state identity is incomplete")
    bitfile = Path(artifacts["bitfile"]["path"])
    if (str(Path(state["bitfile_name"]).resolve()) != str(bitfile) or
            state["bitfile_hash"] != hashlib.sha1(bitfile.read_bytes()).hexdigest()):
        raise SourceError("PYNQ loaded-state artifact does not match")
    if _fpga_state() != "operating":
        raise SourceError("FPGA manager does not report an operating image")
    return {key: state[key] for key in keys}


def _validate_receipt(source, receipt_path):
    try:
        artifacts = _artifacts(source)
        receipt = json.loads(Path(receipt_path).read_text())
        if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or
                receipt.get("boot_id") != _boot_id() or
                receipt.get("artifacts") != artifacts):
            raise SourceError("Prepared receipt is stale or does not match the artifacts")
        preparation = receipt.get("preparation", {})
        if (type(preparation.get("hpd")) is not int or preparation["hpd"] != 1 or
                type(preparation.get("command")) is not int or preparation["command"] != 0 or
                type(preparation.get("vdma_control")) is not int or
                type(preparation.get("vdma_status")) is not int or
                preparation["vdma_control"] & 5 or not preparation["vdma_status"] & 1 or
                preparation["vdma_status"] & DMA_ERRORS):
            raise SourceError("Prepared receipt does not record successful preparation")
        state = _state_identity(artifacts)
        if receipt.get("pynq_state") != state:
            raise SourceError("PYNQ loaded state changed since preparation")
        return receipt
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise SourceError(f"Cannot validate prepared receipt: {error}") from error


def _hardware(source, *, empty):
    import pynq
    descriptions = source.overlay.ip_dict
    def registers(name, expected_type):
        description = descriptions.get("video/" + name, {})
        if description.get("type") != expected_type:
            raise SourceError(f"Prepared capture is missing expected {name}")
        return pynq.MMIO(description["phys_addr"], description["addr_range"])

    dma = registers("axi_vdma", "xilinx.com:ip:axi_vdma:6.3")
    control, status = dma.read(0x30), dma.read(0x34)
    if control & 5 or not status & 1 or status & DMA_ERRORS:
        raise SourceError("Prepared capture requires stopped, reset-clear, error-free DMA")
    command = source.control.registers["capture_control"].read(0)
    if command & 1 or (empty and command != 0):
        raise SourceError("Prepared capture requires disabled capture and reset command state")
    if empty:
        snapshot = source.control.snapshot("prepared_reset_empty_check")
        credit = registers("capture_credit", "xilinx.com:ip:axi_gpio:2.0")
        completion = registers("capture_completion", "xilinx.com:ip:axi_gpio:2.0")
        sequence = registers("capture_sequence", "xilinx.com:ip:axi_gpio:2.0")
        if (credit.read(0) & ~64 or credit.read(8) or completion.read(0) or completion.read(8) or
                sequence.read(0) or sequence.read(8) or
                snapshot["selected_frames"] or
                snapshot.get("frontend_overflow_episodes") != 0 or
                snapshot.get("frontend_underflow_episodes") != 0):
            raise SourceError("Prepared capture requires empty credit and clean source faults")
    return dict(vdma_control=control, vdma_status=status, command=command)


@contextmanager
def _discard_metadata_on_failure(source):
    if source._started or source.native is not None or source.leased or not source.dma_shutdown_safe:
        raise SourceError("Preparation and attach require an inactive source")
    try:
        yield
    except BaseException:
        # Earlier maps can be stale after a download. Cleanup owns no hardware here.
        source.control = source.hdmi = source.pixel_format = None
        for name in ("overlay", "manifest"):
            if hasattr(source, name):
                delattr(source, name)
        raise


def _attach_metadata(source, receipt_path, *, empty):
    with _discard_metadata_on_failure(source):
        receipt = _validate_receipt(source, receipt_path)
        LiteXSource.load_overlay(source, download=False)
        if _validate_receipt(source, receipt_path) != receipt:
            raise SourceError("Prepared receipt changed while attaching")
        _hardware(source, empty=empty)
        if _validate_receipt(source, receipt_path) != receipt:
            raise SourceError("Prepared state changed during hardware checks")
        return receipt


def attach_prepared(source, receipt_path, *, video_drivers=True):
    """Check the preparation ledger and empty hardware before video-driver writes."""
    _attach_metadata(source, receipt_path, empty=True)
    if video_drivers:
        source._initialize_video()


def prepare(source, receipt_path, *, after_reset=False):
    """Load with DMA inactive and assert HPD; after_reset is a caller assertion."""
    if type(after_reset) is not bool:
        raise ValueError("after_reset must be boolean")
    with _discard_metadata_on_failure(source):
        return _prepare(source, receipt_path, after_reset=after_reset)


def _prepare(source, receipt_path, *, after_reset):
    artifacts = _artifacts(source)
    receipt_path = Path(receipt_path)
    if (str(receipt_path.resolve()) in {item["path"] for item in artifacts.values()} or
            not receipt_path.parent.is_dir()):
        raise SourceError("Receipt must be separate from artifacts in an existing directory")
    if not after_reset:
        _attach_metadata(source, receipt_path, empty=False)
    _check_sdk_shutdown()
    receipt_path.unlink(missing_ok=True)
    LiteXSource.load_overlay(source, download=True, video_drivers=False)
    state = _state_identity(artifacts)
    _hardware(source, empty=True)
    import pynq
    description = source.overlay.ip_dict.get("video/hdmi_in/frontend/axi_gpio_hdmiin", {})
    parameters = description.get("parameters", {})
    if (description.get("type") != "xilinx.com:ip:axi_gpio:2.0" or
            any(parameters.get(name) != "1" for name in
                ("C_GPIO_WIDTH", "C_ALL_OUTPUTS", "C_IS_DUAL"))):
        raise SourceError("Prepared capture requires the one-bit fixed-output dual HPD GPIO")
    gpio = pynq.MMIO(description["phys_addr"], description["addr_range"])
    gpio.write(0, 1)
    if gpio.read(0) & 1 != 1:
        raise SourceError("Receiver HPD did not assert")
    hardware = _hardware(source, empty=True)
    if _state_identity(artifacts) != state or _artifacts(source) != artifacts:
        raise SourceError("Prepared artifacts or loaded state changed during preparation")
    receipt = dict(schema_version=1, boot_id=_boot_id(), artifacts=artifacts,
                   pynq_state=state, preparation=dict(hpd=1, **hardware))
    # Publish only after download, hardware checks and HPD assertion succeed.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=receipt_path.parent,
                                         prefix=receipt_path.name + ".", delete=False) as output:
            temporary = output.name
            json.dump(receipt, output, indent=2)
            output.write("\n")
        os.replace(temporary, receipt_path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return receipt
