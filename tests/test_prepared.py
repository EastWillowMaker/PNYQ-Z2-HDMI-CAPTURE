import asyncio
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from hdmi_capture import prepared
from hdmi_capture.sources import CREDIT_ABI, LiteXCreditSource, LiteXSource, SourceError


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    bitfile, manifest = tmp_path / "capture.bit", tmp_path / "manifest.json"
    bitfile.write_bytes(b"bitstream")
    bitfile.with_suffix(".hwh").write_bytes(b"hardware")
    manifest.write_text("{}")
    source = LiteXCreditSource(bitfile, manifest)
    events, banks, descriptions = [], {}, {}

    class Registers:
        def __init__(self, name, values=None):
            self.name, self.values = name, values or {}

        def read(self, offset):
            events.append(("read", self.name, offset))
            return self.values.get(offset, 0)

        def write(self, offset, value):
            events.append(("write", self.name, offset, value))
            self.values[offset] = value

    names = ("axi_vdma", "capture_control", "capture_credit", "capture_completion",
             "capture_sequence", "hdmi_in/frontend/axi_gpio_hdmiin")
    for address, name in enumerate(names):
        descriptions["video/" + name] = dict(phys_addr=address, addr_range=4096,
            type="xilinx.com:ip:" + ("axi_vdma:6.3" if address == 0 else "axi_gpio:2.0"))
        banks[name] = Registers(name, {0x34: 1} if address == 0 else {})
    descriptions["video/hdmi_in/frontend/axi_gpio_hdmiin"]["parameters"] = dict(
        C_GPIO_WIDTH="1", C_ALL_OUTPUTS="1", C_IS_DUAL="1")
    source.overlay = SimpleNamespace(ip_dict=descriptions)
    source.control = SimpleNamespace(registers={"capture_control": banks["capture_control"]},
        snapshot=lambda point: dict(selected_frames=0, completed_frames=0,
            frontend_overflow_episodes=0, frontend_underflow_episodes=0))
    source.control.enable = lambda enabled: banks["capture_control"].write(0, int(enabled))
    overlay, control = source.overlay, source.control
    state = dict(bitfile_name=str(bitfile), bitfile_hash=hashlib.sha1(bitfile.read_bytes()).hexdigest(),
                 timestamp="download-1", active_name="device0")
    environment = dict(boot="boot-1", fpga="operating")
    monkeypatch.setattr(prepared, "verify_litex_artifacts", lambda *args: dict(capture_interface=CREDIT_ABI, source_health_sha256="health"))
    monkeypatch.setattr(prepared, "_boot_id", lambda: environment["boot"])
    monkeypatch.setattr(prepared, "_fpga_state", lambda: environment["fpga"])
    monkeypatch.setattr(prepared, "_raw_state", lambda: copy.deepcopy(state))
    monkeypatch.setitem(sys.modules, "pynq", SimpleNamespace(MMIO=lambda address, length: banks[names[address]]))

    def load(self, download=True, *, video_drivers=True):
        events.append(("download" if download else "metadata", video_drivers))
        self.overlay, self.control = overlay, control
        if download:
            assert video_drivers is False
            state["timestamp"] += "+1"
            for name, bank in banks.items():
                bank.values = {0x34: 1} if name == "axi_vdma" else {}
    monkeypatch.setattr(LiteXSource, "load_overlay", load)
    monkeypatch.setattr(source, "_initialize_video", lambda: events.append(("video",)))
    receipt = tmp_path / "prepared.json"
    return SimpleNamespace(source=source, receipt=receipt, events=events, banks=banks,
                           state=state, environment=environment, load=load)


def initial_prepare(receiver):
    receipt = prepared.prepare(receiver.source, receiver.receipt, after_reset=True)
    receiver.events.clear()
    return receipt


def test_prepare_loads_before_gpio_and_publishes_receipt(receiver):
    receipt = prepared.prepare(receiver.source, receiver.receipt, after_reset=True)
    assert receiver.events[0] == ("download", False)
    assert ("video",) not in receiver.events
    assert json.loads(receiver.receipt.read_text()) == receipt
    assert receipt["preparation"]["hpd"] == 1
    assert receipt["pynq_state"]["timestamp"] == "download-1+1"
    assert receiver.banks["hdmi_in/frontend/axi_gpio_hdmiin"].values == {0: 1}


@pytest.mark.parametrize("after_reset", ["false", 1, None])
def test_reset_assertion_requires_actual_boolean_before_any_work(receiver, monkeypatch, after_reset):
    monkeypatch.setattr(prepared, "_artifacts", lambda source: pytest.fail("artifacts read"))
    with pytest.raises(ValueError, match="boolean"):
        prepared.prepare(receiver.source, receiver.receipt, after_reset=after_reset)
    assert receiver.events == [] and not receiver.receipt.exists()


@pytest.mark.parametrize("parameter", ["C_GPIO_WIDTH", "C_ALL_OUTPUTS", "C_IS_DUAL"])
@pytest.mark.parametrize("value", [None, "0", "2"])
def test_unsupported_hpd_parameters_prevent_gpio_writes_and_receipt(receiver, parameter, value):
    parameters = receiver.source.overlay.ip_dict["video/hdmi_in/frontend/axi_gpio_hdmiin"]["parameters"]
    if value is None:
        del parameters[parameter]
    else:
        parameters[parameter] = value
    with pytest.raises(SourceError, match="HPD GPIO"):
        prepared.prepare(receiver.source, receiver.receipt, after_reset=True)
    assert not receiver.receipt.exists()
    assert not any(event[0] in ("write", "video") for event in receiver.events)


@pytest.mark.parametrize("field,value", [("schema_version", True), ("hpd", True),
    ("command", False), ("vdma_control", False), ("vdma_status", True)])
def test_receipt_numeric_fields_reject_boolean_values(receiver, field, value):
    receipt = initial_prepare(receiver)
    if field == "schema_version":
        receipt[field] = value
    else:
        receipt["preparation"][field] = value
    receiver.receipt.write_text(json.dumps(receipt))
    with pytest.raises(SourceError):
        prepared.attach_prepared(receiver.source, receiver.receipt)
    assert receiver.events == []


def test_attach_checks_hardware_before_video_without_download(receiver):
    initial_prepare(receiver)
    prepared.attach_prepared(receiver.source, receiver.receipt)
    assert receiver.events[0] == ("metadata", True)
    assert receiver.events[-1] == ("video",)
    assert any(event[0] == "read" for event in receiver.events[:-1])
    assert not any(event[0] in ("download", "write") for event in receiver.events)


@pytest.mark.parametrize("bank,offset,value", [("axi_vdma", 0x30, 1), ("capture_control", 0, 1)])
def test_sender_cleanup_after_attach_rejection_never_touches_unowned_image(receiver, bank, offset, value):
    from hdmi_capture.sender import Sender
    initial_prepare(receiver)
    receiver.banks[bank].values[offset] = value
    source = LiteXCreditSource(receiver.source.bitfile, receiver.source.manifest_path,
                               prepared_receipt=receiver.receipt)
    source.start = source.load_overlay
    async def start_and_cleanup():
        sender = Sender(source)
        try:
            await sender.start()
        finally:
            await sender.close()
    with pytest.raises(SourceError, match="stopped|disabled"):
        asyncio.run(start_and_cleanup())
    assert not any(event[0] in ("write", "video", "download") for event in receiver.events)
    assert source.control is None and source.hdmi is None and source.native is None
    assert source.dma_shutdown_safe


@pytest.mark.parametrize("after_reset", [False, True])
def test_prepare_failure_restores_fresh_source_before_caller_cleanup(receiver, after_reset):
    initial_prepare(receiver)
    if after_reset:
        del receiver.source.overlay.ip_dict["video/hdmi_in/frontend/axi_gpio_hdmiin"]["parameters"]
    else:
        receiver.banks["axi_vdma"].values[0x30] = 1
    source = LiteXCreditSource(receiver.source.bitfile, receiver.source.manifest_path)
    try:
        with pytest.raises(SourceError):
            prepared.prepare(source, receiver.receipt, after_reset=after_reset)
    finally:
        source.close()
    assert source.control is None and source.hdmi is None and source.native is None
    assert source.dma_shutdown_safe
    assert not any(event[0] in ("write", "video") for event in receiver.events)


@pytest.mark.parametrize("field,value", [("_started", True), ("native", object()),
                                       ("leased", True), ("dma_shutdown_safe", False)])
def test_active_source_reuse_rejects_before_metadata_replacement(receiver, monkeypatch, field, value):
    initial_prepare(receiver)
    source = receiver.source
    previous = (source.overlay, source.control, source.hdmi)
    setattr(source, field, value)
    monkeypatch.setattr(prepared, "_artifacts", lambda source: pytest.fail("artifacts read"))
    with pytest.raises(SourceError, match="inactive"):
        prepared.attach_prepared(source, receiver.receipt)
    with pytest.raises(SourceError, match="inactive"):
        prepared.prepare(source, receiver.receipt, after_reset=True)
    assert (source.overlay, source.control, source.hdmi) == previous and receiver.events == []


def test_attach_failure_discards_unowned_metadata_references(receiver):
    initial_prepare(receiver)
    source = LiteXCreditSource(receiver.source.bitfile, receiver.source.manifest_path)
    old_overlay, old_control = object(), object()
    source.overlay, source.control = old_overlay, old_control
    receiver.banks["axi_vdma"].values[0x30] = 1
    with pytest.raises(SourceError, match="stopped"):
        prepared.attach_prepared(source, receiver.receipt)
    assert source.control is None and source.hdmi is None and source.pixel_format is None
    assert not hasattr(source, "overlay")
    assert not hasattr(source, "manifest")


def test_failed_rebuild_prepare_never_restores_old_register_map_for_cleanup(receiver, monkeypatch):
    initial_prepare(receiver)
    Path(receiver.source.bitfile).with_suffix(".hwh").write_bytes(b"rebuilt hardware with new addresses")
    source = LiteXCreditSource(receiver.source.bitfile, receiver.source.manifest_path)
    source.overlay = SimpleNamespace(name="old-layout")
    source.control = SimpleNamespace(enable=lambda enabled:
        receiver.events.append(("old-map-write", 0xBAD00000, int(enabled))))
    def failed_rebuild(self, *args, **kwargs):
        receiver.load(self, *args, **kwargs)
        receiver.banks["axi_vdma"].values[0x30] = 1
    monkeypatch.setattr(LiteXSource, "load_overlay", failed_rebuild)
    try:
        with pytest.raises(SourceError, match="stopped"):
            prepared.prepare(source, receiver.receipt, after_reset=True)
    finally:
        source.close()
    assert not any(event[0] in ("write", "old-map-write", "video") for event in receiver.events)
    assert source.control is None and source.hdmi is None and source.native is None
    assert source.dma_shutdown_safe and not receiver.receipt.exists()


def test_successful_attach_guards_preserve_cleanup_after_video_init_failure(receiver, monkeypatch):
    from hdmi_capture.sender import Sender
    initial_prepare(receiver)
    source = LiteXCreditSource(receiver.source.bitfile, receiver.source.manifest_path,
                               prepared_receipt=receiver.receipt)
    source.start = source.load_overlay
    def failed_video():
        receiver.events.append(("video",))
        raise RuntimeError("video initialization failed")
    monkeypatch.setattr(source, "_initialize_video", failed_video)
    async def start_and_cleanup():
        sender = Sender(source)
        try:
            await sender.start()
        finally:
            await sender.close()
    with pytest.raises(RuntimeError, match="video initialization failed"):
        asyncio.run(start_and_cleanup())
    assert source.control is receiver.source.control and source.dma_shutdown_safe
    assert [event for event in receiver.events if event[0] in ("video", "write")] == [
        ("video",), ("write", "capture_control", 0, 0)]


@pytest.mark.parametrize("failure", ["missing", "malformed", "boot", "bitfile", "hwh", "manifest",
                                     "state_hash", "state_path", "state_time", "state_missing", "fpga",
                                     "preparation"])
def test_invalid_receipt_or_state_rejects_before_metadata_or_hardware(receiver, failure):
    initial_prepare(receiver)
    if failure == "missing":
        receiver.receipt.unlink()
    elif failure == "malformed":
        receiver.receipt.write_text("{")
    elif failure == "boot":
        receiver.environment["boot"] = "boot-2"
    elif failure in ("bitfile", "hwh", "manifest"):
        saved = json.loads(receiver.receipt.read_text())
        Path(saved["artifacts"][failure]["path"]).write_bytes(b"replaced")
    elif failure == "state_hash":
        receiver.state["bitfile_hash"] = "wrong"
    elif failure == "state_path":
        receiver.state["bitfile_name"] = "/different.bit"
    elif failure == "state_time":
        receiver.state["timestamp"] = "new-download"
    elif failure == "state_missing":
        del receiver.state["timestamp"]
    elif failure == "preparation":
        saved = json.loads(receiver.receipt.read_text())
        saved["preparation"]["command"] = 1
        receiver.receipt.write_text(json.dumps(saved))
    else:
        receiver.environment["fpga"] = "unknown"
    with pytest.raises(SourceError):
        prepared.attach_prepared(receiver.source, receiver.receipt)
    assert receiver.events == []
    with pytest.raises(SourceError):
        prepared.prepare(receiver.source, receiver.receipt)
    assert receiver.events == []


@pytest.mark.parametrize("bank,offset,value", [
    ("axi_vdma", 0x30, 1), ("axi_vdma", 0x30, 4), ("axi_vdma", 0x34, 0),
    ("axi_vdma", 0x34, 0x11), ("capture_control", 0, 1), ("capture_control", 0, 2),
    ("capture_credit", 0, 1), ("capture_credit", 0, 2), ("capture_credit", 0, 4),
    ("capture_credit", 8, 1), ("capture_completion", 0, 1), ("capture_completion", 8, 1),
    ("capture_sequence", 0, 1), ("capture_sequence", 8, 1)])
def test_unclean_hardware_rejects_before_video(receiver, bank, offset, value):
    initial_prepare(receiver)
    receiver.banks[bank].values[offset] = value
    with pytest.raises(SourceError):
        prepared.attach_prepared(receiver.source, receiver.receipt)
    assert ("video",) not in receiver.events
    assert not any(event[0] in ("download", "write") for event in receiver.events)


@pytest.mark.parametrize("bank,offset,value", [("axi_vdma", 0x30, 1),
    ("axi_vdma", 0x34, 0), ("axi_vdma", 0x34, 0x11), ("capture_control", 0, 1)])
def test_reprepare_never_programs_active_or_unclean_dma(receiver, bank, offset, value):
    initial_prepare(receiver)
    receiver.banks[bank].values[offset] = value
    with pytest.raises(SourceError):
        prepared.prepare(receiver.source, receiver.receipt)
    assert not any(event[0] in ("download", "write", "video") for event in receiver.events)
    assert receiver.receipt.exists()


def test_reprepare_accepts_disabled_toggles_and_replaces_receipt(receiver):
    previous = initial_prepare(receiver)
    receiver.banks["capture_control"].values[0] = 6
    current = prepared.prepare(receiver.source, receiver.receipt)
    assert current["pynq_state"]["timestamp"] != previous["pynq_state"]["timestamp"]
    assert current["preparation"]["command"] == 0
    assert ("video",) not in receiver.events


def test_state_race_during_metadata_construction_rejects_before_driver(receiver, monkeypatch):
    initial_prepare(receiver)
    def raced_load(self, *args, **kwargs):
        receiver.load(self, *args, **kwargs)
        receiver.state["timestamp"] = "raced"
    monkeypatch.setattr(LiteXSource, "load_overlay", raced_load)
    with pytest.raises(SourceError, match="changed"):
        prepared.attach_prepared(receiver.source, receiver.receipt)
    assert receiver.events == [("metadata", True)]


def test_state_race_during_hardware_reads_rejects_before_driver(receiver, monkeypatch):
    initial_prepare(receiver)
    bank = receiver.banks["axi_vdma"]
    original = bank.read
    def raced_read(offset):
        value = original(offset)
        receiver.state["timestamp"] = "raced"
        return value
    monkeypatch.setattr(bank, "read", raced_read)
    with pytest.raises(SourceError, match="changed"):
        prepared.attach_prepared(receiver.source, receiver.receipt)
    assert ("video",) not in receiver.events


@pytest.mark.parametrize("counter", ["selected_frames", "completed_frames",
    "frontend_overflow_episodes", "frontend_underflow_episodes"])
def test_unclean_endpoint_counters_reject_before_driver(receiver, counter):
    initial_prepare(receiver)
    snapshot = dict(selected_frames=0, completed_frames=0,
                    frontend_overflow_episodes=0, frontend_underflow_episodes=0)
    snapshot[counter] = 1
    receiver.source.control.snapshot = lambda point: snapshot
    with pytest.raises(SourceError, match="empty credit"):
        prepared.attach_prepared(receiver.source, receiver.receipt)
    assert ("video",) not in receiver.events


def test_failed_download_invalidates_previous_receipt(receiver, monkeypatch):
    initial_prepare(receiver)
    def failed_load(self, download=True, **kwargs):
        if download:
            assert not receiver.receipt.exists()
            raise RuntimeError("configuration failed")
        receiver.load(self, download=download, **kwargs)
    monkeypatch.setattr(LiteXSource, "load_overlay", failed_load)
    with pytest.raises(RuntimeError, match="configuration failed"):
        prepared.prepare(receiver.source, receiver.receipt)
    assert not receiver.receipt.exists()


def test_prepared_source_uses_attach_path(receiver, monkeypatch):
    initial_prepare(receiver)
    receiver.source.prepared_receipt = receiver.receipt
    receiver.source.load_overlay()
    assert receiver.events[-1] == ("video",)
    assert not any(event[0] == "download" for event in receiver.events)


def test_prepared_source_gpio_only_load_preserves_read_only_contract(receiver):
    initial_prepare(receiver)
    receiver.source.prepared_receipt = receiver.receipt
    receiver.source.load_overlay(download=False)
    assert receiver.events[0] == ("metadata", True)
    assert any(event[0] == "read" for event in receiver.events)
    assert not any(event[0] in ("video", "write", "download") for event in receiver.events)
    assert receiver.source.hdmi is None


def test_receipt_cannot_replace_an_artifact(receiver):
    bitfile = Path(receiver.source.bitfile)
    with pytest.raises(SourceError, match="separate"):
        prepared.prepare(receiver.source, bitfile, after_reset=True)
    assert bitfile.read_bytes() == b"bitstream" and receiver.events == []


def test_old_sdk_shutdown_registers_reject_before_unknown_image_access(receiver):
    receiver.state["shutdown_ips"] = {"old_ip": dict(base_addr=0x12340000)}
    with pytest.raises(SourceError, match="shutdown IP"):
        prepared.prepare(receiver.source, receiver.receipt, after_reset=True)
    assert receiver.events == [] and not receiver.receipt.exists()


def test_initial_prepare_accepts_absent_sdk_state_before_download(receiver, monkeypatch):
    def raw_state():
        if not any(event[0] == "download" for event in receiver.events):
            raise FileNotFoundError("no saved state")
        return copy.deepcopy(receiver.state)
    monkeypatch.setattr(prepared, "_raw_state", raw_state)
    prepared.prepare(receiver.source, receiver.receipt, after_reset=True)
    assert receiver.receipt.exists() and receiver.events[0] == ("download", False)


def test_raw_state_preserves_original_saved_hash(tmp_path, monkeypatch):
    state = dict(bitfile_name="absent.bit", bitfile_hash="original-saved-hash")
    (tmp_path / "global_pl_state.json").write_text(json.dumps(state))
    monkeypatch.setitem(sys.modules, "pynq.pl_server.global_state", SimpleNamespace(STATE_DIR=str(tmp_path)))
    assert prepared._raw_state() == state


def test_post_download_hardware_failure_does_not_publish_receipt(receiver, monkeypatch):
    def bad_load(self, *args, **kwargs):
        receiver.load(self, *args, **kwargs)
        receiver.banks["axi_vdma"].values[0x30] = 1
    monkeypatch.setattr(LiteXSource, "load_overlay", bad_load)
    with pytest.raises(SourceError, match="stopped"):
        prepared.prepare(receiver.source, receiver.receipt, after_reset=True)
    assert not receiver.receipt.exists()
    assert not any(event[0] in ("write", "video") for event in receiver.events)


def test_gpio_only_overlay_load_never_constructs_video(monkeypatch, tmp_path):
    from hdmi_capture import sources
    source = LiteXCreditSource(tmp_path / "capture.bit", tmp_path / "manifest.json")
    descriptions = {"video/" + name: dict(type="xilinx.com:ip:axi_gpio:2.0",
                    phys_addr=address, addr_range=4096)
                    for address, name in enumerate(("capture_control", "capture_counts", "capture_errors"))}
    descriptions["video/axi_vdma"] = dict(type="xilinx.com:ip:axi_vdma:6.3",
                                         parameters=dict(C_INCLUDE_S2MM="1", C_INCLUDE_MM2S="0"))
    overlay = SimpleNamespace(ip_dict=descriptions, is_loaded=lambda: True)
    calls = []
    monkeypatch.setattr(sources, "verify_litex_artifacts", lambda *args: dict(capture_interface=CREDIT_ABI))
    def load(path, *, download):
        calls.append(download)
        return overlay
    monkeypatch.setitem(sys.modules, "pynq", SimpleNamespace(__version__="3.0.1", Overlay=load,
                                                           MMIO=lambda *args: object()))
    monkeypatch.setattr(source, "_initialize_video", lambda: pytest.fail("video driver constructed"))
    LiteXSource.load_overlay(source, download=True, video_drivers=False)
    assert calls == [True] and source.hdmi is None


def test_prepare_cli_passes_explicit_reset_assertion(monkeypatch, capsys):
    from hdmi_capture import sender
    calls = []
    def prepare(source, path, *, after_reset):
        calls.append((source.bitfile, source.manifest_path, path, after_reset))
        return dict(preparation=dict(hpd=1))
    monkeypatch.setattr(prepared, "prepare", prepare)
    sender.main(["prepare", "--bitfile", "capture.bit", "--manifest", "manifest.json",
                 "--receipt", "prepared.json", "--after-reset"])
    assert calls == [("capture.bit", "manifest.json", "prepared.json", True)]
    assert json.loads(capsys.readouterr().out)["input_mode_verified"] is False


def test_capture_cli_passes_prepared_receipt_without_loading(monkeypatch):
    from hdmi_capture import sender
    sources = []
    async def run(self, *args):
        sources.append(self.source)
    monkeypatch.setattr(sender.Sender, "run", run)
    sender.main(["--source", "litex-credit", "--bitfile", "capture.bit",
                 "--manifest", "manifest.json", "--prepared-receipt", "prepared.json"])
    assert len(sources) == 1 and sources[0].prepared_receipt == "prepared.json"


def test_capture_cli_rejects_receipt_for_other_sources():
    from hdmi_capture import sender
    with pytest.raises(SystemExit):
        sender.main(["--source", "synthetic", "--prepared-receipt", "prepared.json"])


class ReadyClock:
    def __init__(self, arrive=None):
        self.now, self.arrive = 0, arrive

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.arrive is not None:
            arrive, self.arrive = self.arrive, None
            arrive()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_ready_wait_refuses_stale_marker_paths(tmp_path, kind):
    marker = tmp_path / "ready"
    if kind == "file":
        marker.touch()
    elif kind == "directory":
        marker.mkdir()
    else:
        marker.symlink_to(tmp_path / "missing")
    with pytest.raises(SourceError, match="absent"):
        prepared.wait_ready_file(marker, 1)
    assert marker.exists() or marker.is_symlink()


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_ready_wait_rejects_nonregular_arrival(tmp_path, kind):
    marker = tmp_path / "ready"
    arrive = marker.mkdir if kind == "directory" else lambda: marker.symlink_to(tmp_path / "missing")
    clock = ReadyClock(arrive)
    with pytest.raises(SourceError, match="regular"):
        prepared.wait_ready_file(marker, 1, clock=clock, sleep=clock.sleep)


def test_ready_wait_accepts_new_file_and_preserves_it(tmp_path):
    marker = tmp_path / "ready"
    clock = ReadyClock(marker.touch)
    prepared.wait_ready_file(marker, 1, clock=clock, sleep=clock.sleep)
    assert marker.is_file()


def test_ready_timeout_never_constructs_a_source(tmp_path, monkeypatch):
    from hdmi_capture import sender
    marker = tmp_path / "ready"
    clock = ReadyClock()
    wait = prepared.wait_ready_file
    monkeypatch.setattr(prepared, "wait_ready_file", lambda path, timeout:
        wait(path, timeout, clock=clock, sleep=clock.sleep))
    monkeypatch.setattr(sender, "LiteXCreditSource", lambda *args, **kwargs: pytest.fail("source constructed"))
    with pytest.raises(SourceError, match="Timed out"):
        sender.main(["--source", "litex-credit", "--bitfile", "capture.bit", "--manifest", "manifest.json",
                     "--prepared-receipt", "receipt.json", "--wait-ready-file", str(marker),
                     "--ready-timeout", "0.2"])
    assert not marker.exists()


def test_marker_arrival_still_revalidates_receipt_boot(receiver, monkeypatch):
    from hdmi_capture import sender
    initial_prepare(receiver)
    marker = receiver.receipt.with_name("ready")
    def arrive():
        receiver.environment["boot"] = "different-boot"
        marker.touch()
    clock = ReadyClock(arrive)
    wait = prepared.wait_ready_file
    monkeypatch.setattr(prepared, "wait_ready_file", lambda path, timeout:
        wait(path, timeout, clock=clock, sleep=clock.sleep))
    async def run(self, *args):
        self.source.load_overlay()
    monkeypatch.setattr(sender.Sender, "run", run)
    with pytest.raises(SourceError, match="stale"):
        sender.main(["--source", "litex-credit", "--bitfile", str(receiver.source.bitfile),
                     "--manifest", str(receiver.source.manifest_path), "--prepared-receipt", str(receiver.receipt),
                     "--wait-ready-file", str(marker)])
    assert receiver.events == [] and marker.exists()


@pytest.mark.parametrize("options", [
    ["--source", "synthetic", "--wait-ready-file", "/tmp/ready"],
    ["--source", "litex-credit", "--wait-ready-file", "/tmp/ready"],
    ["--source", "synthetic", "--ready-timeout", "1"],
    *[["--source", "litex-credit", "--prepared-receipt", "receipt.json", "--wait-ready-file", "/tmp/ready",
       "--ready-timeout", value] for value in ("0", "-1", "nan", "inf", "901")]])
def test_ready_cli_rejects_invalid_source_or_timeout(options):
    from hdmi_capture import sender
    with pytest.raises(SystemExit):
        sender.main(options)
