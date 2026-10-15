# Release clients without waiting for another frame

The009 real-board smoke received15 exact HDMI frames over7.343seconds.
The immediately following strict qualifier received EOF before its first
header, while the sender continued acquisition and later stopped safely.
The original009 qualifier remains failed with zero delivered frames and one
transport error. Sender source errors0, invalid baseline6 unchanged/FIFOs0,
DMA cleanup true, post-run ext4count0 and persistence hash unchanged.

## Reproduction and diagnosis

Ranked possibilities before changing behavior: old client slot not yet freed;
old-handler cleanup affecting a new client; sender duration ending too early.
The45-second sender lifetime continued long past the7-second smoke and the
failed reconnect, ruling out its timer as this failure's cause. Source shows
the old handler never read the peer StreamReader: EOF could remain buffered
while it waited for the next ready frame. The active-client guard then rejected
the replacement. The identity check already prevented old cleanup from clearing
a different writer, so no evidence supported the second hypothesis.

A real local TCP regression delivers one frame, pauses further source output,
closes that client and requires its slot to clear before connecting a second
client. The initial harness incorrectly let its only frame precede connection;
that first red was a test-setup timeout and is not regression evidence. The
corrected harness waits for the first accepted connection before releasing its
first frame. It fails before the fix with StreamReader EOF and _client still
held after0.5seconds, rather than failing initial frame acquisition. The saved
red-corrected log is the relevant before result. After the fix both an empty
peer and unsolicited peer bytes reconnect with newer frame IDs/same session,
without stopping capture or counting normal EOF as a network error.

## Impact and execution order

Read sender.py main:355→Sender.run:208→Sender.start:193→the registered
asyncio server callback _serve_client:139→create_task:147→_watch_disconnect:128.
These are more than three upstream edges to the verified CLI entry. Graph
records the direct _serve_client→_watch_disconnect edge; the asyncio callback
invocation is verified from source and actual socket tests, not resolved as an
inbound graph edge. SDK/event-loop internals are not claimed fully traced.

The watcher uses bounded1024-byte reads to ignore client input, calls the
existing network-transport abort helper, and cancels only its TCP handler.
The handler cancels/joins its watcher in finally, waits for writer closure,
then clears its own slot and task record. Normal EOF does not increment
network_errors; reset/read errors and existing write errors still can. The
metric remains an error-observation count, not a distinct disconnect count.
The live-client rejection guard remains in front of admission. A reconnect
before the old EOF is processed can still be rejected; no takeover guarantee
or automatic client retry was added. Protocol framing and corruption handling
are unchanged in source; actual client/protocol tests provide evidence for the
covered paths, not a general proof of no side effects.

Acquisition remains Sender.start:204→_capture:82. It copies completed sample
pixels into an immutable network frame and releases the DMA sample in its own
finally. Cancelling a TCP handler does not cancel this capture task. Global
close atsender.py233 still cancels acquisition, aborts the active writer,
cancels/joins client handlers, then calls source.close. The credit source's
raw-halt-before-frontend-stop/buffer-free and unsafe-DMA hold are untouched;
existing lifecycle tests passed. No board DMA process was force-killed.

Graph coverage at2026-10-15T17:00:13Z found no recorded gaps for sender.py,
client.py,sources.py and sender/client/reconnect tests. Operator scripts are
excluded and read directly. No graph completeness claim is made for dynamic
PYNQ dispatch or external callbacks. Read errors in the new watcher, sustained
malicious incoming traffic, and every cancellation interleaving were not
individually exercised. Hosted CI and new HDL/CAD runs were not performed.

## Verification and deployment

Corrected before test:1failed at stale-client assertion. After fix focused
sender/client/reconnect:33passed, then34passed after adding peer-data coverage.
Full host suite:306passed/1skipped in2.89seconds before that additional
parameter case. The skipped module requires Migen/LiteX, both absent from the
host client venv; this is not a new gateware pass. No RTL changed in this fix.

Deployed v11 archive SHA256
01e66269264fe0eeab36cf7451c56ab33e785576256e4217ca91237f5012ea13.
Board readback hashes matched. Before reprogramming, raw S2MM CR0x15010/
SR0x11001 proved RS0/Halted1 after009 cleanup. Reload017 then a software HPD
pulse produced startup underflow1, so that preparation is retained and was
not accepted as clean capture startup. Loaded a fresh017 instance without
another pulse; no capture buffer existed during these preparation steps.
010 starts the same7-second smoke→10-second strict qualifier with the v11
sender, a fresh source03=150seconds and original pixel/health checks.
The native startup path rejects nonzero FIFO baseline before allocating DMA.
Actual010 outcome is pending; neither the software fix nor15 smoke frames
constitutes the600-second criterion or complete M1 qualification.


## Actual010 hardware result

The original coordinator now completes smoke→new strict-client connection
without inserting a sleep or retry between them. Smoke passed, then21/21
exact distinct frames passed over10.395406seconds (2.020123FPS), zero pixel,
metadata and transport failures. All21 source-accounting records validated.
The original009 EOF result remains failed; it was not overwritten or retried
inside the strict observation window. This is a real-board regression pass in
addition to the deterministic local paused-source test.

The45-second sender ended normally with source errors0, cleanup errors0,
network errors0 and dma_shutdown_safe=true. Startup invalid_frames3 remained3;
startup/current FIFO over/underflow0. Before/after ext4errors_count0 and the
16MiB persistence file hash matched. The current010 coordinator reports all
short smoke/criterion/cleanup/storage checks true. The qualification script's
physical_source_sequence_verified flag remains false: independent KMS/optical
and hardware buffer-association evidence must be considered separately. A
10-second run is not the600-second criterion and full M1 remains false.

Prepared011 with the same017/v11 runtime and checks:650-second sender,
7-second smoke→600-second qualifier, minimum600distinct frames/1FPS,
hard deadline660seconds, source04=720seconds. This only changes bounded test
durations/result paths/resource sampling, not protocol or pixel acceptance.
Actual011 outcomes remain pending. No new HDL build or timing claim is made.
