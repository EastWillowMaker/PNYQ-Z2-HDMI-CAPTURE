#!/usr/bin/env python3
"""Verify or temporarily configure only the known Digilent HDMI source output."""

import argparse
import copy
import json
from pathlib import Path
import sys


def read_configuration(state, resources):
    """Turn Mutter state into an applyable configuration, including hidden modes."""
    serial, monitors, logicals, properties = state
    if resources[0] != serial:
        raise ValueError("Display state changed while reading; retry")
    by_connector = {monitor[0][0]: monitor for monitor in monitors}
    outputs = {output[4]: output for output in resources[2]}
    crtcs = {crtc[0]: crtc for crtc in resources[1]}
    modes = {mode[0]: mode for mode in resources[3]}
    configs = []
    for x, y, scale, transform, primary, specs, _props in logicals:
        entries = []
        for spec in specs:
            connector = spec[0]
            monitor = by_connector[connector]
            current = [mode[0] for mode in monitor[1] if mode[-1].get("is-current")]
            if len(current) == 1:
                mode_id = current[0]
            else:
                # GetCurrentState filters small modes even while they are active.
                output = outputs[connector]
                raw = modes[crtcs[output[2]][6]]
                mode_id = f"{raw[2]}x{raw[3]}@{raw[4]:.3f}"
            settings = {}
            for source, target in [("color-mode", "color-mode"),
                                   ("rgb-range", "rgb-range"),
                                   ("is-underscanning", "underscanning")]:
                if source in monitor[2]:
                    settings[target] = monitor[2][source]
            entries.append([connector, mode_id, settings])
        configs.append([x, y, scale, transform, primary, entries])
    return {"serial": serial, "configs": configs,
            "properties": {"layout-mode": properties["layout-mode"]},
            "identities": {name: list(monitor[0])
                           for name, monitor in by_connector.items()}}


def source_identity_kind(original, connector):
    identity = original["identities"].get(connector)
    if identity is not None and identity[1:3] == ["DGL", "DigilentDVI-2"]:
        return "base"
    if identity is not None and identity[1:] == ["DGL", "LiteX VGA", "0x00000000"]:
        return "litex_vga"
    raise ValueError("Selected connector is not a known DGL capture sink")


def candidate(original, resources, connector, mode):
    kind = source_identity_kind(original, connector)
    output = next(output for output in resources[2] if output[4] == connector)
    by_id = {item[0]: item for item in resources[3]}
    if kind == "litex_vga" and any(
            tuple(by_id[index][2:4]) != (640, 480)
            or f"640x480@{by_id[index][4]:.3f}" not in {"640x480@60.000", "640x480@59.940"}
            or by_id[index][5] & (16 | 32) for index in output[5]):
        raise ValueError("LiteX VGA sink must advertise only supported progressive VGA timings")
    matching = [by_id[index] for index in output[5]
                if tuple(by_id[index][2:4]) == (640, 480)
                and f"640x480@{by_id[index][4]:.3f}" == mode]
    if not matching:
        raise ValueError("Requested 640x480 mode is absent from connector resources")
    result = copy.deepcopy(original)
    selected = [logical for logical in result["configs"]
                if any(entry[0] == connector for entry in logical[5])]
    if len(selected) != 1 or len(selected[0][5]) != 1:
        raise ValueError("Selected output must be enabled and not mirrored")
    if selected[0][3] != 0:
        raise ValueError("Selected output must have normal orientation")
    selected[0][2] = 1.0
    selected[0][5][0][1] = mode
    return result


def other_configuration(configuration, connector):
    return [logical for logical in configuration["configs"]
            if not any(entry[0] == connector for entry in logical[5])]


def restore_candidate(current, snapshot, connector):
    if snapshot.get("format") != "hdmi-source-mutter-v1" \
            or snapshot.get("connector") != connector:
        raise ValueError("Snapshot format or connector mismatch")
    original = snapshot["original"]
    kind = source_identity_kind(current, connector)
    if current["identities"] != original["identities"]:
        raise ValueError("Monitor identities changed; refuse snapshot restoration")
    if other_configuration(current, connector) != other_configuration(original, connector):
        raise ValueError("Another monitor changed; refuse snapshot restoration")
    selected = [logical for logical in current["configs"]
                if any(entry[0] == connector for entry in logical[5])]
    if len(selected) != 1 or len(selected[0][5]) != 1:
        raise ValueError("Selected output must remain enabled and not mirrored")
    restored = copy.deepcopy(original)
    if kind == "litex_vga" and any(entry[1] not in {"640x480@60.000", "640x480@59.940"}
                                 for logical in restored["configs"] for entry in logical[5]
                                 if entry[0] == connector):
        raise ValueError("LiteX VGA restoration must remain in supported VGA modes")
    restored["serial"] = current["serial"]
    return restored


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connector", required=True)
    parser.add_argument("--mode", choices=["640x480@59.940", "640x480@60.000"],
                        default="640x480@59.940")
    parser.add_argument("--apply", action="store_true",
                        help="Apply a temporary mode after verification")
    parser.add_argument("--snapshot", type=Path,
                        help="New original-state snapshot; required with --apply")
    parser.add_argument("--restore", type=Path,
                        help="Restore a previously saved snapshot temporarily")
    args = parser.parse_args(argv)
    if args.apply and args.snapshot is None and args.restore is None:
        parser.error("--apply requires --snapshot")
    if args.restore and (args.apply or args.snapshot):
        parser.error("--restore cannot be combined with --apply or --snapshot")
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        def call(method, parameters=None):
            return bus.call_sync(
                "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                "org.gnome.Mutter.DisplayConfig", method, parameters, None,
                Gio.DBusCallFlags.NONE, 5000, None).unpack()

        def apply(config, method):
            logicals = []
            for x, y, scale, transform, primary, entries in config["configs"]:
                typed_entries = []
                for connector, mode, properties in entries:
                    typed = {key: GLib.Variant("b" if key == "underscanning" else "u", value)
                             for key, value in properties.items()}
                    typed_entries.append((connector, mode, typed))
                logicals.append((x, y, scale, transform, primary, typed_entries))
            props = {key: GLib.Variant("u", value)
                     for key, value in config["properties"].items()}
            parameters = GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})",
                                      (config["serial"], method, logicals, props))
            return call("ApplyMonitorsConfig", parameters)

        state, resources = call("GetCurrentState"), call("GetResources")
        original = read_configuration(state, resources)
        if args.restore:
            snapshot = json.loads(args.restore.read_text())
            config = restore_candidate(original, snapshot, args.connector)
        else:
            config = candidate(original, resources, args.connector, args.mode)
        apply(config, 0)  # Verify through Mutter; no modeset or persistence.
        report = {"verified": True, "applied": False, "requested": config}
        if args.apply or args.restore:
            # Serial rejects a topology/configuration change since verification.
            if call("GetCurrentState")[0] != original["serial"]:
                raise ValueError("Display state changed after verification; retry")
            if args.apply:
                with args.snapshot.open("x") as handle:
                    json.dump({"format": "hdmi-source-mutter-v1",
                               "connector": args.connector, "original": original}, handle,
                              indent=2)
                    handle.write("\n")
            apply(config, 1)  # Temporary only; never method 2 (persistent).
            after = read_configuration(call("GetCurrentState"), call("GetResources"))
            report.update(applied=True, after=after)
            if after["configs"] != config["configs"] or after["properties"] != config["properties"]:
                print(json.dumps(report, indent=2))
                raise ValueError("Applied state differs from request; retain snapshot for restoration")
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, ImportError, KeyError, StopIteration) as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception as error:
        # Gio failures include stale serials, denied configuration and missing APIs.
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
