# RGB frame protocol v1

The baseline transport is one TCP connection from a single client to the board.
It carries complete, uncompressed RGB888 frames. TCP stream boundaries have no
meaning: implementations loop over partial reads and writes. A protocol error,
timeout, EOF, or socket error ends the connection; close and reconnect rather
than scan for magic bytes. A new connection resets client frame-ID tracking.

The sender rejects another connection while one client is active. It monitors
peer EOF separately from frame acquisition, so a disconnected client releases
its slot even while the source waits for a frame. This closes only the TCP
handler; capture continues with its bounded ready slot. Incoming client bytes
are ignored in bounded reads and are not commands. A normal peer EOF is not
counted as a network error. Reconnection can still be rejected before the old
connection's EOF has been processed; retry explicitly after that rejection.

## Wire layout

The 20-byte fixed prefix uses network byte order, Python format `>4sB3xIII`:

| Offset | Bytes | Meaning |
| --- | --- | --- |
| 0 | 4 | Magic ASCII `LHDC` |
| 4 | 1 | Version, exactly 1 |
| 5 | 3 | Reserved, exactly zero |
| 8 | 4 | Metadata byte length, 1 through 8192 |
| 12 | 4 | Payload byte length, 3 through 6,220,800 |
| 16 | 4 | CRC32 of payload, Python `zlib.crc32` |

UTF-8 JSON metadata follows, then the packed pixel payload. Each pixel is R, G,
B, one unsigned byte per channel; rows run left to right, top to bottom. No wire
row padding exists. CRC32 detects accidental payload damage; it does not
authenticate a peer or cover metadata. This initial transport is for a dedicated
trusted link and supplies no encryption or access control.

## Metadata

All fields below are required. Extra finite JSON fields are allowed within the
same total metadata limit, for counters or future observational data. Extra
fields cannot override required fields. Duplicate JSON keys anywhere are invalid.
NaN, Infinity, numeric float overflow, malformed UTF-8 and malformed JSON are
invalid. Booleans are not accepted as integer fields.

| Field | Value |
| --- | --- |
| `width`, `height` | Integers, 1..1920 and 1..1080 respectively |
| `pixel_format` | Exactly `RGB888` |
| `stride` | Integer exactly `width * 3` |
| `frame_id` | Integer 0..2^64-1; strictly increases within each connection |
| `timestamp_ns` | Integer 0..2^64-1 |
| `timestamp_clock` | Nonempty string naming the actual clock |
| `timestamp_sample_point` | Nonempty string naming the actual sampling event |
| `flags` | List of strings; observational, with no implicit feature activation |
| `source_origin` | `synthetic` or `hdmi` |
| `source_color_format` | Nonempty string, e.g. `RGB` or `unknown` |
| `source_quantization_range` | `unknown`, `full`, or `limited` |
| `baseline_only` | Boolean; true for M0 PYNQ and synthetic evidence |

`payload_length` must equal `height * stride`. Width, height and stride are
validated before payload allocation. Supporting a 1920x1080 envelope is a parser
limit, not a promise that the hardware source supports that mode. The agreed
initial source is 640x480p60. Packed representation performs no scaling, gamma,
range adjustment or channel conversion; source characterization is separate.

`frame_id` identifies producer acquisitions, not necessarily every input HDMI
frame. The client checks increasing IDs. The protocol decoder does not retain
connection state. Optional `session_id` identifies a producer run, and
`source_sequence` may be null when source-frame counting is unavailable. These
fields must not be used to claim source drop counts that hardware cannot observe.
Board and host clocks must not be subtracted as if synchronized.

## Python interface and ownership

`Frame(rgb, metadata)` exposes a writable, owned NumPy `uint8` array with shape
`(height, width, 3)`. Each receive owns separate payload storage; later reads do
not mutate an earlier frame. `encode_frame(rgb, metadata)` returns immutable wire
bytes. `send_frame(sock, rgb, metadata)` validates before its first socket write.
Noncontiguous input arrays are packed in row order. The caller must hold exclusive
ownership of the source array until serialization completes; this layer cannot
prevent a DMA engine or another thread from overwriting the input concurrently.

`read_frame(sock)` reads one complete validated frame. `ProtocolError` subclasses
`ValueError`; `FrameEOF` subclasses `EOFError`. Socket errors and `socket.timeout`
propagate. A positive finite socket timeout bounds the entire frame I/O operation,
including partial progress, and the original socket timeout is restored. A
blocking socket with timeout `None` has no deadline. Nonblocking sockets are
unsupported. Callers should set a positive timeout and close on every failure.

The receive allocates at most one bounded payload bytearray and bounded metadata
storage, plus decoder/array overhead. Serialization makes a payload copy and a
complete wire-message copy; this is a measured-baseline design rather than a
zero-copy transport. Sender metadata is JSON-encoded incrementally and rejected
when its encoded length exceeds 8192 bytes.

## Behavior impact and verification boundaries

Before this addition the repository had no frame decoder or executable capture
protocol. Version 1 newly accepts bounded RGB888 frames with the metadata above,
including arbitrary supported dimensions and optional observational JSON fields.
Dispatch is direct to `read_frame`, then validated dimensions, bounded payload
read, CRC verification and an owned array. There is no implementation lookup or
fallback format, NULL payload or no-op decoding. Unsupported formats/versions,
oversized frames, invalid packing, forbidden integer types and corrupted payloads
raise before delivery. There is no peer authorization check; trusted-link access
is a deployment assumption. Unknown extra flags cannot enable operations.

`tests/test_protocol.py` exercises split and coalesced frames, RGB channel/row
patterns, noncontiguous sender arrays, malformed metadata and prefix fields,
early rejection before payload reads, truncation at multiple stages, CRC errors,
partial/zero writes, a total-operation deadline and real socket timeout/EOF.
These establish transport/parser behavior only. They do not establish HDMI mode
acceptance, DMA/cache correctness, source sequence freshness, RGB range fidelity,
hardware authorization, LiteX integration or physical sustained performance.
Those paths require source, client and board integration evidence. No old parser
history exists to reproduce a previous decoder result.

Local verification on 2026-10-15: `.venv/bin/python -m pytest
tests/test_protocol.py -q` passed all 56 cases in 0.25 seconds, with NumPy 2.5.4
and pytest 9.1.1. `compileall` and `git diff --check` also passed. This is local
software evidence; hosted CI remains unverified. Subsequent physical board
execution delivered synthetic and real HDMI frames over Ethernet with zero
protocol errors in the recorded batches; see [M0 evidence](results/2026-10-15/m0-bringup.md).
Negative parser tests remain host-side evidence, and later pixel/startup and
board stability failures prevent a sustained-path qualification claim.
