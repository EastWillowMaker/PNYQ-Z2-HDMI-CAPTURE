# Progress and handoff

2026-10-17 — Real1080p loop bring-up; final-accounting fix under verification.

The user confirmed J9OUT→J10IN cabling with “Done”. The guarded switch loaded
build005 after verifying the old image idle, then prepared it without native
video drivers. Fixed-clock observation measured150VSYNC edges/5.011851seconds
(about29.93Hz), clean geometry/FIFO counters and halted DMA. A first real capture
with the old copy implementation passed37distinct exact1080p RGB888 frames in
20.084306seconds,1.842234FPS, zero pixel/metadata/transport errors.

That board run nevertheless exited1: the fixed50ms final proof could observe
only one30Hz edge and reported a cleanup error after safe DMA halt/free. The
original failed result is retained. Commit `cfd30d3` scales the proof to three
input periods, keeping the two-edge requirement and halt-before-free order.
Deterministic red/green coverage includes30/60/59.94Hz phases and stopped input;
focused252pass, fullhost592pass/1optional Migen/LiteX skip. The new runtime is
verified at `/tmp/hdmi-capture-1080p30-003/src`; the unchanged overlay and current
receipt remain under `/tmp/hdmi-capture-1080p30-002`. See
[bring-up and original failure](results/2026-10-17/1080p30-loop-bringup-001.md).

Board verification of the fix passed: optimized001 delivered50exact frames in
20.157482seconds,2.480469FPS, then exited0/DMA safe/zero source-cleanup-network
errors. Held-lease001 passed stable A through188native edges, rejected another
read before arm and received a different exact B after ACK. Its component
extension verified20more images: median DMA arm→observed halt42.207ms,
read57.604ms, copy99.009ms. Raw cached TCP passed629.465Mbps with every payload
hash checked. See [performance](results/2026-10-17/1080p30-loop-performance.md).
[Real GUI/BMP](results/2026-10-17/1080p30-gui-hdmi-001.md) passed the actual Save
button and every decoded RGB byte; its bounded sender ended0/safe/zero errors.

The uninstrumented600-second qualification is running on port9044, senderPID4315
with650-second bounded duration, source `cfd30d3`, exec20131 for the host pipeline.
The exact child argv was checked before starting read-only resource sampler4443.
The first52seconds passed104exact frames at about2FPS. Final criterion, safe
shutdown and post-storage/kernel checks remain pending. Logs use fresh
`artifacts/operator/1080p-sustained-001-*`; board logs/receipt remain in002,
runtime is003. Never restart or signal native work merely on observer timeout.
The transfer server63088 was
stopped after checking exact argv/UID (PID2122742), sessionexit15; no task HTTP
server remains. Do not use the old “no PL load” or physical-wait statements below
as current state.

Preserved earlier1080p CAD/deployment checkpoint:

2026-10-17 — 1080p30 clock-constraint diagnosis and copy measurements.

Commit `029c403` resolves the false synchronous reset associations using a
minimal TX BD harness. Full build004 from that revision passed BD validation,
synthesis and routing, but strict final export rejected repeated Timing38-249
critical warnings: the serializer's packaged XDC incorrectly creates its serial
clock from the pixel clock. Their actual branches share an MMCM parent. The
internal bitstream in004 is not a deployable artifact and has not been loaded.
An isolated routed-checkpoint probe removed exactly that false constraint;
SerialClk then inherited the correct371.25MHz MMCM clock without that warning.
Commit `7935b71` applies the staged-IP adaptation with a strict source anchor,
configuration assertions and a bound XDC hash. Fresh full build005 completed
from immutable `artifacts/1080p30-source-005` into `artifacts/1080p30-loop-005`
(console in the sibling `.console.log`), exit0. The paired package passed
strict checks: setup0.539ns/hold0.013ns, all56bus-skew paths MET, no critical
CDC/DRC/run diagnostics or unconstrained internal endpoints. Artifacts were
transferred and all three hashes verified on the board; no PL load yet. See
[build005](results/2026-10-17/1080p30-build-005.md). No warnings are waived.

Commit `4cff9ec` makes the held-lease checker explicitly profile-aware;20tests
passed, including a full1080p held buffer and rejection of VGA geometry before
ACK. Hardware lease observation remains pending. Board CPU-only measurements
found an exact NumPy channel-copy improvement from269.953ms to100.198ms median
on ordinary1080p arrays. Commit `0acd289` applies that change; a direct board
measurement of the production method confirmed267.649ms→99.748ms median,
2.68× faster with exact pixels and independent read-only output. Full host
tests574pass/1optional skip; focused build/mode/HWH47pass. Native DMA and real
HDMI measurements remain pending; see
[copy measurements](results/2026-10-17/1080p30-copy-profile.md).

The integrated profile, DMA, fixture and output-pattern changes are committed
as `df5410d`. Host tests passed565/1skip; the skipped Migen/LiteX module passed
all45tests in the pinned generator environment. The separate profile/HWH set
passed42tests before the first build and44after the copied-clock metadata fix.
Output simulation checked two full1080p frames and reset/release. See the
[local checkpoint](results/2026-10-17/1080p30-local-checkpoint.md).

Fresh builds001/002 stopped at BD validation and produced no bitstream. The
first exposed missing/wrong clock and reset metadata plus the monitor's fixed
VGA pixel-clock declaration. Commit `0d35411` corrects those declarations;
`b097ae9` then corrects the shared asynchronous reset association. Failure
records are retained in dated results. A new full build003 ran from
immutable `artifacts/1080p30-source-003`, output
`artifacts/1080p30-loop-003`, console
`artifacts/1080p30-loop-003.console.log`. It also stopped at BD validation:
the shared asynchronous reset was still inferred as synchronous to SerialClk
at the pattern's pixel-clock reset input. No bitstream was produced. These
failures preceded the reset fix and build004 described above. No
critical-warning checks were waived.

The board's known VGA image was independently checked against its existing
receipt: RS0/Halted1, command2/gate disabled, matching boot/artifact state and
no saved shutdown IPs. No PL reconfiguration has occurred. The original source
package is staged at `/tmp/hdmi-capture-1080p30-001/src`; a newer verified
`0acd289` runtime and held-lease tools are at `/tmp/hdmi-capture-1080p30-002`.
Two bounded synthetic senders ended normally and no
sender remains. The15second full1080p network run delivered47frames at
3.131661FPS/155.851493Mbps, zero protocol errors; the expected partial frame
at the duration cutoff was reported and excluded. The GUI saved one full-size
uncompressed BMP whose decoded RGB bytes matched the exact click-time frame.
These are synthetic checks, not real HDMI results. See
[measurements](results/2026-10-17/1080p30-synthetic.md).

Both temporary HTTP servers are stopped. The second server (exec session80410)
served only `artifacts/deploy/1080p30-002`; after all transfers, its exact argv
and normal-user ownership were checked before SIGTERM. No sender is running.
New source archive SHA256 is
`23b86f94231cc66c41d42db3042d3c141f60ed31ea51f0e3013a4d473c06fb2a`.
The latest UART check reconfirmed passwordless sudo, the same boot ID and no
sender or CPU benchmark process. Board time remains2022; use host dates and
monotonic durations for evidence. Do not request authentication again. Physical
OUT-to-IN cable change was requested after the verified build005 export and
awaits the user's actual confirmation. Keep the Hub/Micro-B connected.
Do not start native HDMI configuration before the real source clock is stable.
Real1080p/loop/BMP/performance qualification remains pending.

2026-10-16 — Next scope implementation in progress.

The user confirmed 1080p RGB888 at a feasible progressive input timing,
at least 600 new exact frames over ten minutes with average delivery >=1 FPS,
uncompressed BMP saving in a Python desktop viewer, board passwordless sudo,
and a same-board HDMI OUT-to-IN pattern loop. See requirements.md for the
accepted boundaries; the VGA completion below remains historical evidence.

Commit `337f9d8` records the scope and installs the board's explicitly approved
`xilinx ALL=(ALL:ALL) NOPASSWD: ALL` rule. A separate UART verification with
credential caching disabled returned UID 0 and `visudo -c` passed. The login
password and host sudo policy were not modified. The board still has the same
boot ID as the completed VGA run; a read-only process check found no capture
sender. No new overlay has been loaded.

Commit `276c702` adds the desktop viewer and shared uncompressed BMP writer,
including CLI BMP capture. The focused host suite passed 93 tests, including
1080p synthetic pixel equality, TCP capture and a Tk smoke test. The editable
package was installed into the project `.venv`; `hdmi-capture-viewer --help`
succeeded. The first no-build-isolation install failed because this venv lacks
setuptools; normal isolated build with the explicit public PyPI index passed.
See [viewer evidence](results/2026-10-16/desktop-viewer.md).

Primary-source research selects 1080p30 at 74.25 MHz as the first candidate,
not a hardware guarantee. Mode-aware build/runtime/fixture changes and an
optional PL output pattern are in progress. Gateware for 1920x1080 was
generated at `artifacts/1080p30-gate-001/litex_capture.v` with the pinned
dependencies, using
`artifacts/clean-replay-001/artifacts/gate-venv/bin/python`. Its RTL SHA256 is
`e1f4202e8077a917d7d3a7214b2b0b6266fa5a1e3ffb33e45dd9112e7fcbaad1`.
New-mode CAD, output-loop execution and sustained real 1080p capture remain
unverified. Preserve `docs/results/2026-10-15/m1-recovery-scanout.log`.

2026-10-16T22:21:40+08:00 — Accepted fixed-mode M1 complete.

PC Python receives real HDMI IN RGB888 through the LiteX single-credit gate,
parked VDMA/PS DDR and PS Ethernet. Normal019 passed1,201distinct exact frames
in600.300346s at2.000665FPS, zero pixel/metadata/transport errors and safe stop.
Held-buffer015, clean-source public workflow023, user-confirmed physical loss024
and explicit restart025 close the separate ownership/reproduction/fault gates.
025passed21exact/10.109394s, new session/source IDs, zero normal source/cleanup/
network errors, DMA halt/storage/kernel checks and sourceexit0/VTrestoration.
No new authentication was needed for the final restart. The root024→025 chain
passed. A final read-only check found no active board capture sender and ext4
errors0; the bounded PC worker ended normally via stopfile after source exit.

Read[the completion report](results/2026-10-16/m1-completion.md) and its aggregate
JSON before the historical checkpoints below. Per-run fullM1false flags and
failed original observers remain unchanged; aggregate scope is fixed VGA near60Hz,
not arbitrary HDMI. Runtime3343dac; clean source exportad6c966; fresh clean017
paired artifacts/build replay. Host tests490pass/1optional skip, focused60pass.
No production capture code changed after that runtime; host readiness90s and
fatal-log guard were verified separately and exercised by clean023.

Use quickstart.md and prepared-capture.md, with a live supported source before
native configuration, fresh paths, normal preparation/restart and litex-credit.
The documented source is240s to budget90s readiness+90s sender+cleanup. No
capturing service is left running; start an authorized sender for a new session.
Do not reload unknown/active DMA or force-kill native resources. Unknown startup
native skips/absolute optical-native mapping, unknown source format/range,
unsupported-geometry hardware NOT_RUN, VTC startup clock requirement, ignored
post-safe-cleanup UIO warning and timing/CDC/external-I/O limits remain explicit.
Web, bypass and LCD C are later milestones; do not start them as follow-on work
without their own agreed scope. No push/PR or external capture upload was made.
The unrelated untracked m1-recovery-scanout.log remains untouched.

2026-10-16T22:14:52+08:00 — Confirmed loss024 passed; explicit restart025 running.
User confirmed HDMIIN-only5s unplug/reconnect, Hub/MicroB unchanged.101exact
frames then boundaryEOF102.938s; no partial transport/pixel/metadata failure.
RootexpectedfailstopTrue/exit1; exact knownfinalproofcleanup1 recordedafter
safehalt/free, rawCR0x15010/SR0x11001/command2gateoff/storage/kernel/noSIGBUSpass.
Source03continued240s/exit0/VTrestored; separate verified.json passes physical
scope while originalpending-humancontroller remainsunchanged. No native signal.

Initial025hostprereq observer1676747 mistook verifiedsudo ancestors ofexisting
worker forcompeting sources, beforeanysource04/proof/marker/nativework. Stopped
ONLYthisverifiednormal-userobserver(emptychildren) andsavedNOT_RUN evidence.
Immutable025b helper now validates exactrootworker+2sudoancestor PID/start/argv/
UID/ancestry; otherDRMsourcesstillreject. Actual025bPID1678254queuedsource04
180s/id2500000 beforedeadline; no newPCauth or rootworker edit. Root025already
stagedbyfixedchain, normalprepare-afterfreshKMS/9032/sender45s/client10s. Await
actualroot/client/source/VT finalresults; don'tstage live025 files. Existing
worker1656056deadline349638; aftersource04actualexit/restore, use stopfile toend
idleworker normally. FullM1 notyetmarkedcomplete; finalaudit isunderway.

2026-10-16T22:06+08:00 — Clean023 public workflow/restart independently verified.
41exactRGB frames/20.309945s/2.018715FPS; completegitexportad6c966, cleanmodule
paths/hashes/publicwait->prepare->exec andcleanpublictrigger90/qualifier20.
Newsession/opticalIDs/endpointNPYverified. Actualsenderexit0/zeroerrors/rawhalt/
storage/source240exit0/VTrestore. Originalroot/controllerfalsekept: historical
kernelabort rolledout1->0; exact161lineoverlap/41newlinesprove no newabort.
Separate m1-017-clean-023-verified.json passes boundedstartup/restartscope with
hashes oforiginalresults. FullM1stillfalse. No newPython/XRT/CADbuildclaim.

Physical024rootchain+optionalrestart025stagedwhileboardauthvalid, exacthashes;
initialfilesystemwaitonly. Userexplicitlyready; source03isrunning240/id2400000,
receiverready~52s and3exactframesby53.483s, beforemanual100scue. User instructed
HDMIIN-only unplug5s after100s fromVTswitch; Hub/MicroBunchanged. Awaitactual
sourceerror/client/root/desktop andhumanconfirmation, don'tstage live024files.
Host024parsed diagnostics+boundaryEOF nowpreserveallframeevidence; partialEOF
rejects. No changes toSDK/runtime or liveworker. ExistingPCworker021rejects
continuationaftersourceexit1; do notqueue04if03failed. Optional025rootwaiter
startsONLYafter024safeexpectedstop andneedsnewPCone-runworker/localPCauthif
03failed. That concretePC-onlyhelperisbeingprepared; no newboardauthrequired
foralreadylaunchedrootchain. PCworker021deadline349638 (~22:17), nevereditlive.

2026-10-16T21:53+08:00 — Mode021 exact-before/fail-stop/safe-halt evidence saved.
47exactRGB frames; real advertised25200->25175nominalKMS timing transition.
EOF46.923ms aftermodesetbegin, before1.578776sdriverack; client raced eventlog
and reportsfailed. Rootalsofailed strictcleanup0 but actualsourcefault finalproof
rethrownAFTERsafehalt/free (counter1), sameknownclassificationas020. One invalid
sourceframe rejected/notdelivered; overrunattributionunknownafterfault. Sender
exit1/noSIGBUS/rawCR0x15010/SR0x11001/command6gateoff/storage/kernelclean. Source
exit0/VTrestore. Originalfailedverdictspreserved; analysisandreportlinkactualtime.
No automaticrecovery or unsupportedgeometry hardwareclaim. Rootchain021->022
endedwithoutstarting022; clean022NOT_RUN. Boardauthstandalone sudo-n-v passed
21:51, so no newhumanpasswordrequiredyet. Cleanfullgitarchivead6c966 stagedas
/tmp/hdmi-capture-clean-023 (archiveSHA583c5fcc4a953588a50baa4362ab3b2da717c59f97d49e5ddb0cd32481aecf70).
New023literalpublicwait->prepare->CLI helperbeingprepared/reviewedbeforestart;
no clean023DMA/source yet. ExistingPCworker1656056 readydeadline349638.048468968,
source02reserved240s/id2300000, safeoldsource01terminal. KeepPCwindowopen/cables.

2026-10-16T21:47+08:00 — Sender-readiness fix verified locally.
Trackedtrigger now defaults90s for combinedpreparation/native startup, with
strict --sender-timeout integer1..120; UART/process bounds add10/20s. Source
readiness timeout remains independent. No native kill or retry added. Real
accelerated shell delayed50s regression failsbefore/passesafter; missing/late
fatal guards pass. Literal ERE brace escape fixes an exposed fatal-log guard.
Focused60pass; fullhost490pass/1optional skip. No capture/RTL change. Report
results/2026-10-16/sender-readiness-wait.md. Mode021 PC wizard still requires
initialEnter andlocalPCsudo aslastchecked; no mode source/result yet. Board
mode waiter900s starts21:35, so verify remainingtimebefore a late retry.

2026-10-16T21:46+08:00 — Loss020 failed observation; safe physical stop verified.
User confirmed HDMI IN-only unplug/reconnect (~5s); Hub/Micro-B unchanged.
The45s startup observer timed out before actual sender listening, so client
never started. Original020controller/root failure preserved; source acquired60
without consumer, then exit1/source fault. DMA safe/rawhalt/gateoff/storage/
no new externalabort/VTrestore passed; noSIGBUS. Cleanup counter1 is the final
source-proof error rethrown AFTER safe teardown, not a failed halt/free in
this trace; separate hash-linked analysis and report retain that distinction.
The old019source worker ended normally via stopfile after source02 exit/restore.
Mode021root waiter12297 remains bounded900s from21:35. New mode host1642092
waits for its PC-only root worker; Ptyxis window/wizard1642285 is at initial
Enter prompt. User must pressEnter then enter PCsudo locally; no UART/board
reauth required while waiter islive. Mode source120s with automatic nominal
25200->25175kHz transition at75s. All cables stay connected. No current mode
source at21:45. Test worker uses isolated binary and does not modify originals.
Trackedtrigger readiness90s fix/regression is being tested in parallel; no
new production capture behavior change. See latest result reports.

2026-10-16T21:38+08:00 — Normal019 passed; HDMI-loss020 running.
The production v14 /3343dac sender and fresh clean-replay017 overlay delivered
1,201 distinct exact RGB888 frames in 600.300346 seconds (2.000665 FPS).
All pixel, metadata, received-window transport and accounting checks passed.
Sender exit0, safe DMA shutdown, independent raw halt/gate-off, storage/hash,
no new external abort, source exit0 and desktop restoration passed. Startup
native skips and independent optical-to-native mapping remain unknown. The
inherited post-cleanup UIO destructor warning is retained in the sender log.
Results: results/2026-10-16/m1-017-normal-019*. A detailed independent report
is being written; this sustained criterion does not complete full M1.

The user explicitly confirmed readiness for physical loss020. The existing
coordinator1626527 queued source02 on bounded root worker1615628 after019 passed
and restored the desktop. Source180s/id2100000; user instructions: wait75s
from VT switch, unplug only PYNQ HDMI IN for5s, reconnect; Hub/Micro-B stay
connected. Await actual results and separate confirmation of the action.
Do not mark a physical pass from observer EOF alone. Do not contend UART
while the coordinator prepares/collects. Mode021/clean022 root chain is staged
with exact script hashes and filesystem-only waiting (mode supervisor12297,
900s from21:35); no mode marker/source has been sent. New PC mode worker
requires a separate local PC credential and the old019 worker to finish;
never replace or interrupt its live source. Full M1 remains incomplete.

2026-10-16T21:24:08+08:00:USER HOME;019 FORMAL600s CAPTURE RUNNING.
018expired withoutsource/preparation/client; NOT_RUN envelope+actualrootresult
saved, no failedpixelrun. New019two-stagewizard completedboard+PCauth, sameboot
1dd70e40/ext4count0; nooldcaptureprocess found. FreshKMS source720s/frame2000000,
rootpreparesAFTERvalidatedKMSflips then unchangedv14/3343dac sender650s/port9026.
Strict600s/min600/>=1FPS/hard660 client islive PID1616141, coordinator1614239.
Atfirstcheck74exactframes/metadatapassed; notyetlongpass. Results m1-017-normal-019
areLIVE; do notstage/commitunfinishedframeJSONL orclaimcompletebeforefinalresult.
PCrootworker1615628 deadline348038.537233211 (hostmonotonic), max6runs/30min;
keepwindow/cablesconnected. Boardrootpostchecks don'tneedfurtherauthforcurrentrun.
Newhelper019addsinitialstoragegate/preparation-child timeoutreporting; production
packageunchanged. Modeprototype delegatedseparateignoredoutput only, no current
fixture/wrapper/rootworker modification orhardwareexecution. PhysicalHDMI-only
loss/restart/mode tests stillopen. No UARTwhilehosttrigger/nativeauthownsit.

2026-10-16T09:15:07+08:00:016 STARTUP FAIL;017 STEADY-SOURCE RESTART PASS;018 AWAITS PC.
016 selected0/no client: KMS transitionlatched FIFOunderflow1; preparedguard
correctlyrejected beforevideo. Independentfixedclock CR0x10002/SR0x10001/gateoff,
SDhealthy. Originalsupervisorfailure/senderexit1 preserved; hostreadonlyobserver
1272172 stoppedalone because echoedpendingtextmaskedterminalresult; no native/
source signals. Separate017 normalprepare aftersourcewassteady +realCLI passed
21exact/10.340019s/2.030944FPS, senderexit0/DMAhalt/storage/kernelpassed.
Source03 completed720s/exit0/VTrestored; oldrootworker014 finishednormally.
Updatedqueued docs waitfreshmarker->normalprepare->sender usingtrackedcommands;
no runtimecode/counterwaiver/retryloop. Report normal-016-warm-017-report.md.
018rootwaiter+hostcoordinator1279991 arelive; PC-onlywizard1280821 open. NewPCauth
questionpending; no newsource/600sclient yet. Rootwaiter900s andhost850s start
nearhostmonotonic302247.8 (~09:07), verifyactualremainingtimebeforeuserretry.
Window PYNQ normal 018 - PC password only. Source018720s/strict600s unchanged;
boardauthnotneededwhilewaiterexists. Keepallcablesconnected; no sourceconcurrency.
ReadonlyDRMcachedinventoryfoundVGA60/59.94 only(clock25200/25175); no othergeometry.
Currentfixture/worker cannotrequesttransition. FullM1false; mode/loss/manualgaps
remain. No physicalHDMIavailabilityanswer received; do notunplug Hub/Micro-B.

2026-10-16T08:54+08:00:015 HELD-CREDIT HIL PASS; FINAL NORMAL RUN PREPARING.
ActualtrackedcheckerCLIexit0 andwrapperpassed:6Aobservations stableBGR/RGBhash,
heldIDs/parkedVDMA while native325->444 (+119edges); ACK thenexactdifferentB
optical1700078 vs1700070/native451 vs324. Dwell1s plus measuredoverhead; not
independentoptical-to-nativeIDproof. Source02exit0/VTrestore; rawsafehalt/storage/
no newexternalabort. Report m1-017-lease-015-report.md andevidence saved.
No replyyet to physicalcableavailability; proceedingwithnonmanual600snormal016,
source03planned720s. Supervisor/coordinatorbeingprepared beforeexecution. Board
sudo-n-v preflight passed/sameboot/ext4errors0; no newauthenticationneedednow.
Keepallcablesconnected. Mode/geometrygapcannotbeexercisedbyfixedcurrentworker;
no binary/wrapperreplacementunderliveprivilegedworker. FullM1stillfalse.

2026-10-16T08:49+08:00:014 REAL PREPARED SHORT PASS; COLLECTOR ERROR PRESERVED.
41 exact/distinctRGB frames20.108463s/2.038942FPS, all opticalIDs matchKMS and
accountingvalid. Freshreplay017pair/source3343dac through trackedprepare/receipt/
readytrigger/sender. SafeDMAclose and rawCR0x15010/SR0x11001/gateoff command2;
SDpersistence/ext4count0/no newexternalabort/sourceexit0/VTrestored.
Originalcontroller failed finalroot0600receipt fetch only. Readonlysudo supplement
saved receipt/verifiedprocessabsence; originalfailedcontroller unchanged. Sender
shell exitcode notcollected; inheritedUIOdestructorwarning preservedafterclose.
Report results/2026-10-16/m1-017-prepared-014-report.md. FullM1false.
Rootworker1259511 remainsbounded30min/deadline302719; do not replace itsfixture.
Lease015 helper is now running session51888; no UART contention. Next gates:
heldbuffer proof, physicalHDMI-onlyloss/restart, mode inputgap, final600seconds.

2026-10-16T08:44+08:00:USER RETRY; BOARD AUTHENTICATION REACHED STAGING.
Old014wizard/HTTP processes were absent; no local/board014 stage existed.
Read-only UART confirmed unchanged boot1dd70e40, ext4errors0 and expiredsudo.
Restarted direct-link HTTP8766 and one existing014wizard, PID1257893; user
opened miniterm and exited. Stage helper PID1258058 is now running. Do not
contend UART. No capture pass is established yet; inspect stage results and
controller/source artifacts before continuing. V14 archive hash reverified.
See results/2026-10-16/prepared-014-retry-001.json. All cables stay connected.

2026-10-16T03:41:37+08:00:014 CANDIDATE UPDATED TO V14; STILL BEFORE AUTH.
Commit3343dac corrects prepared attach: global unselected completed_frames may
advance while waiting for input; selected-frame/selected-credit completion
must remainzero. Root reproduced failure against isolated e180171 source;
current fullhost466pass/1optional skip. No RTL/source-comment changes.
Immutable v14 source3343dac archive SHA256:
306f8d3234721bfa174cd2e2df66c5f7ef17ab55de2b3802eb2f3c5bced0080f.
All archive members, artifact pair, checksum pipeline and helper syntax pass.
Fresh replay017 pair unchanged and still not hardware-qualified. V13 preserved,
not run; stage-prepared-014.py now targets v14. Package/preflight report a4613f0.
Current process1103733 remains alive at initial local prompt, with no miniterm
child or prepared-014 output directory. No boardstage, source or DMA started.
The existing pending authentication question/window remains the next action;
do not open another auth flow or claim a source-ready hardware result.
Short normal014 must pass with cables connected before lease/loss/mode/final
600second tests. Full M1 remains incomplete. See prepared-counter-guard.md and
prepared-v14-package.json under results/2026-10-16.

2026-10-16T03:34:50+08:00:014 NEW AUTH WINDOW READY; NO PRE-AUTH TEST TIMER.
013terminalNOT_RUN preserved. Unused013wizardonly wasclosedafterexactPID/empty
childcheck; noUARTclient/nativeprocess killed. Newwizard PID1103733:
artifacts/operator/run-prepared-014.sh, titlePYNQ tracked capture - board then PC.
Questionpending: userboard sudo-v/Ctrl+] thenPCsudo; firstnormal120s source,
90s sender/20s strictframes, keepallcablesconnected. OUT artifacts/operator/prepared-014
DOESNOTEXIST untiluserauth->stage. No board preparation/capture coordinator yet.
V13 archive f5417929152efcff9a71ae64059079cff19af9dcfb9c7abae41eb4aa093bdca9
contains tracked8a90bc0 runtime + freshreplay017pair andchecker, pureartifactverifyPASS.
Specificbootstrap checksoldboot1dd70e40/oldloadedpairledger/storage/RS0Halted1gateoff
before knownold017PLreload, then actualtrackedprepare--after-reset makesreceipt.
Changedboot/state aborts ratherthanprobeunknownHW. Newcapture uses realCLI, no
operatorcustomsource. AfterPCauth rootworker max6runs/30min, each<=720s; first120s,
continuesawaitingnextrequestwithper-runexitstatus, abortifVTrestoreunverified.
Coordinator startsONLYafterboardauth soovernightwaitingwontexpiretestagain.
Do NOTtouchUARTwhilehumanminitermactive; monitorlocalfilesandPIDs only.
Report prepared-014-auth-ready.md/preflightJSON. HILnewpair/flow/lease NOT_RUN.

2026-10-16T03:20+08:00: TRACKED READY PIPELINE HOST PASS;013 NOT_RUN.
Sender --wait-ready-file/--ready-timeout blocks before sourceconstruction; host
trigger_prepared_capture.py validatesfreshKMS and waits actualboardTCPbindbefore
client. DefaultknownPYNQvenv paths+fullqueuedcommands in prepared-capture.md;
quickstart usesdirectKMS, privateendpoints. Finalhost465pass1skip/4.03s;131focused,
5docshellblocks syntaxpass; no hardwareproof yet. Report prepared-trigger-integration.
013coordinatorPID847111/session70733 TERMINAL exit1 after30minreadinesswait.
No source.ready/run01/authlaunchlog existed; not-runJSONpreserves evidence. Old
wizardPID847290 maystillwaitEnter; helperhaltsifcoordinatorterminal, noDMA/source.
Do NOTaskduplicateauth untiluserresponds; usefreshnamedtestthen. Lastknownboard
rawsafehalt/gateoff after012, boot1dd70e40; recheck actualstatebeforeloading.
Fresh017cleanreplay finished606.745s/exited0+routedpostreviewpass: setup/hold
0.401/0.014ns,56skewMET,0criticalCDC/DRC,retainedwarningsdocumented. BothHLS15RTL
exactmatchold017;9manifesthashes/source/vendorintegrityverified. NEWPAIRNOTLOADED:
bit ae3a65d77b1662fedef9ffbc62dd9484cdd8a155af136596da3e6b695fb6846e,
hwh 3bfbbf124960ec932a4a53bb4fcb4a5969b89b9a96d6329143bdfc8442eef9a6.
Output artifacts/clean-replay-017-20261016-0308/checkout/artifacts/m1-build-001.
Nextrealwork: freshauth->trackedprepare/shortfirstframe->physical loss/restart,
heldcreditproof/mode tests->final600s unchangedcriterion; fullM1false.

2026-10-16: TRACKED PREPARE/ATTACH + LEASE CHECK HOST PASS.
New sender prepare --receipt [--after-reset] and --prepared-receipt validate
boot/artifact/rawPYNQ ledger identity and stopped/emptyhardware beforevideo.
No-unknown-MMIO initialreset assertion is explicit; receipt is a softwareledger,
not hardwarebuild-ID proof. SavedSDKshutdownmaps reject; fixed-outputHPD TRI
is not read. Failed inactive guards discard unowned/stale maps, so finally-close
cannot disable existingcapture or writeoldaddresses afterreprogramming. Active
owners reject before refschange. New bounded tools/check_credit_lease.py records
heldrawbuffer/IDs/VDMA/nativeprogress, guardsrearm, compares2exactpatterns and
holds unsafeDMArefs oncleanup failure. Hostfinal413pass1skip;79prepared and18
leasecases; actualproductionprepare/attach/lease NOT_RUN. See new prepared-capture,
credit-lease-check and results/2026-10-16/prepared-lease-integration.md.
013stillwaits userauth via immutabledeployedv12; no newDMA. Newfull017isolated
freshHLS/CADreplay delegated to replay_017, nohardwareactions. Keepgoalactive.

2026-10-16T01:38:01+08:00:011 NORMAL600s PASS;012 HDMI LOSS FAIL.
011 received1201 exact distinct frames/600.368226s/2.000439FPS, allmetadata and
source-ID correlation passed. Senderexit0/DMAcleanuptrue, independent raw halt
confirmed; storageafterpass. FullM1false. Source008/run04 exit0/VTrestored.
012 user CONFIRMED HDMI-only unplug/replug5s, Hub/Micro-B untouched.88 exact
frames then sender SIGBUS(-7) in native VTC mode via _healthy; kernel external
abort. Sourcechildexit1, misleading outerworker0, VTrestored. Storagehealthy.
Emergency fixed-clock halt PASS RS0/Halted1/gateoff; no source/sender active.
Currentboot1dd70e40. v12 fix removes runtime native VTC read only; startup mode
checks and LiteX geometry/FIFO/sequence/VDMA checks remain.5-case red regression
then focused93pass/fullhost312pass1skip; adding isolated counter guards.
v12 source/archive staged and hashes matched; privileged013 preparation PENDING.
Both board and PC sudo now require local auth.013 fusedwizard prepared at
artifacts/operator/run-hdmi-loss-013.sh; fixed900s rootwaiter prevents boardauth
expiry between prepare and KMS ready. Source120s; manualHDMI-only at45s/5s.
Do not contend UART while userauthwindow active.316hostpass1skip,45RTLpass. Fix/evidence commit6cfe75c.
Coordinator PID847111/session70733 is live waiting actualKMSready;
localwizard PID847290 opened for user boardauth then PCauth. UART reserved
for human until miniterm exits. Root helper not yet authenticated/run. No new overlay or DMA since raw012 safe stop.
Report results/2026-10-16/capture-011-loss-012-report.md; raw011/012 preserved.
No forced kill/reload while DMA unsafe; current raw recovery did prove safe.

2026-10-16T01:06:38+08:00:010 HARDWARE SHORT PASS.
Same smoke→immediate reconnect, no sleep/retry:21/21exactdistinctframes in
10.395406s/2.020123FPS, pixel/metadata/transporterrors0/accounting21validated.
Senderexit0/networkerrors0/sourceerrors0/cleanuptrue; startupinvalid3unchanged/
FIFOs0. Storagebeforeaftercount0/filehashcorrect. Source03stillfinishing150s;
wait restore beforequeue04. Preparing011 now: boardprepareexec96493 (Halted
before fresh017load,noHPDpulse), coordinator exec6531 waitsfreshsource04.
011supervisor650s/strict600s>=600newframes>=1FPS/harddeadline660, source720s.
No change to parser/pixel/health checks. Check prepare completion and worker
remainingbudget beforequeuing04; useralreadyinformed12min. Source008rootworker
582356 deadline274424.54(~01:24). KeepHub/windowopen; no newauth currentlyneeded.
Codefix+tests+008/009/010evidence preparinglocalcommit. FullM1false pendinglong
run and remainingphysicalmode/loss/bufferassociation/resource evidence.

2026-10-16T01:04:49+08:00:009 smoke15exactframes PASS,
next10squalifier EOF/0frames FAIL; senderlaterexit0/DMAcleanuptrue/storageafter
pass. Confirmed sender ignored readerEOF until another frame/write. RealTCP
regression with pausedsource fails oldcode atstaleclient assertion; new bounded
EOFwatcher aborts onlyTCPwriter/cancels itshandler and releases slot. Liveextra
clientstillrejected; acquisition/immutablecopy/DMAcleanup unchanged in source.
Tests33pass, extendedpeerdata34pass; fullhost306pass/1skip(Migen/LiteX absent).
v11 archiveSHA01e66269...12ea13 deployed/hashverified. Warm017reload+HPDpulse
had startupunderflow1 (preservedfailureprepare); fresh017loadwithoutrepeatpulse
completed, noDMA.010 coordinator exec30337+source008/run03=150s/id1200000 now
runs originalstrictsmoke→10scheck; nonzeroFIFObaseline wouldrejectbeforebuffer.
Read artifacts/operator/capture-010-coordinator.log/results prefix
m1-017-newcard-attach-010. Rootworker582356 alive deadline274424.54(~01:24),
source03returns~01:06. If010 pixel+cleanup+storagepass, freshload then prepare
source04=720s/650s sender for600scriterion; no newuserauth needed ifcachevalid.
Do not skip the original009 failure or weakenhealthchecks. Report:
results/2026-10-16/reconnect-010-report.md. Productionfix uncommittedpending010.

2026-10-16T00:56:38+08:00: retry008 INPUT PASS.
PCauth completed; source01 XR24/VGA25200 exited0/VTrestored. Nativeconstructor
success640x480 in~1.061s; VTCdetectoractive0x01e00280, edges37682→38464/~13.03s,
invalid4unchanged/FIFOs0/selected0, allsampledDMA RS0/Halted1. No buffer/capture.
Freshboard sudo-n-v PASSED (no additionalhumanneeded), sameboot/ext4count0/no
oldsender. Staged009 attachedsender/supervisor45s/resourcehelper withhashchecks.
Started capture009 coordinator exec84447 and queued source008/run02=150s,
id1100000 after01normalrestore. It runs7ssmoke then10sstrictdiagnostic, native
cleanup/storage checks. Outcomes pending; do notmarkM1complete fromshortpass.
Results docs/results/2026-10-16/m1-017-newcard-attach-009-*; coordinator log
artifacts/operator/capture-009-coordinator.log. Sourceworker582356 alive/30min
budget, keepwindowopen and Hubconnected. No boardUART contention withcoord.
Input evidence native-source-008-* and report are saved; pendingchangesuncommitted.

2026-10-16T00:54:29+08:00: user requested retry.
Fresh UART confirms sameboot1dd70e40, ext4count0, rootwaiter1793 still waiting
(boardmonotonic1217.60 vs waiterstart702.84). EDID stillDGL/VGA/SHA3b01e13a.
Session008 has only original request01: no ready/run/result/finished, no active
PCsource/authwindow. Hostcoordinator558062 stillwaiting; PCsudo-n needsauth.
Reopened exactly one PYNQ VGA retry - PC password only terminal using unchanged
start-kms-source-session-008.sh. No new evidence names/reusedcapture and no
boardreauth needed while currentwaiterbudget remains. Usermust enter PCsudo
locally and keepwindowopen. Rawpreflight artifacts/operator/native-source-008-
retry-preflight.log (copy in results/2026-10-16). Current rootwaiter expires near
01:00; localcoordinator timeout shortlybefore. If delayed, inspect actual logs
and state rather than claiming the probe ran. No overlay reload/DMA requested.

2026-10-16T00:46:34+08:00: user boardauth completed,
actual receiver006 load/HPD PASS RS0/Halted1/gateoff/nobuffers. Host initially
stillnonDGL so006 correctlyqueuednothing. One softwareHPDpulse007 refreshed
PC EDID toDGL/LiteXVGA, only640x480 modes, SHA3b01e13a...de31f6. Lock0→1 but
nativeVSYNC0 across8samples; no capturepass. Originalrootworker494498 ended
beforedeadline for unrecordedreason;007 stoppedbeforequeuing03. Hostsudo-n
requiresauth. Started VERIFIED boardrootwaiter PID1793 using existingauth:
fixed nativeprobe only after session008 ready marker, max900s/noDMA. Opened
PYNQ VGA probe - PC sudo only with NEW boundedsource008/request01=90s,id1000000.
User PCsudo pending; keepwindowopen. NO boardreauth needed for this waiter.
Coordinator exec1074 waits actualKMSready thenmarker/nativecollection/VTreturn.
Result artifacts/operator/native-source-008/summary.json; source in
kms-source-session-008. New prototype compile/syntaxpassed, rootwaitingreadback
passed, source/native outcomespending. Do not reuse006/007 failureevidence.
Full report results/2026-10-16/fresh-card-input-diagnosis.md preserves all.

2026-10-16 00:41 Asia/Taipei: user CONFIRMED PYNQ Micro-B shares the USB-C HDMI
Hub. Hub removal explains the board reboot; replug005 is not HDMI-only evidence.
Keep Hub connected; future loss stimulus at HDMI cable with power/UART intact.
Preflight sameboot1dd70e40, ext4count0/helperhashmatch; board sudo requiresauth.
Opened PYNQ receiver - board auth only with prepare-shared-hub-006.sh; user
sudo-v/Ctrl+] then immediate fixedboot017+HPD prepare, no DMA/hostsudo. Do not
contend UART while wizard open. Watcher session88428 waits preparation, DGL
EDID, live boundedsourceworker and remainingdeadline, then stages nativeprobe
and queues unused source03/90s VGA. It records input/VTC/halting only, no capture
buffers. artifacts/operator/shared-hub-006/summary.json records actual result.
New helper/watcher syntax/compilepassed, runtimepending. If worker~00:48 expires,
watcher refuses request03. Physical rootcause clarified; prior input-init bug
remains unresolved. See fresh-card-input-diagnosis.md for dispatch/guards.

2026-10-16 00:37 Asia/Taipei: physical USB-C replug005 observed disconnect then
reconnect, but PYNQ also has NEW boot1dd70e40-85cc-4c9b-a2e2-03b9814e290f,
uptime61s and erased/tmp deployment. Asked user whether board reset/power/UART
was also touched; no agent reboot was sent. Current FPGA stateunknown, so do
not reuse previous boot Halted/loaded-overlay assumptions. EDID now256B,
SHA1b05659c...c80dc, manufacturerzero/nameblank/1080p preferred, notDGL.
No source03 or capture queued; keep sink identity guard. Saved current dmesg:
journal unclean/corrupt and FAT dirty warnings, ext4errorcount0/16MiBhashstill
correct. Cause of reboot/media health not established. Restored existing NIC
profile after ifindex12→13; re-staged unchanged017/v10 via linklocal HTTP8766
(old8765 server scope stale), all hashesmatch. New fixedboot preparation helper
prepare-after-replug-005.py compiled/staged but NOT RUN; needs real board sudo
auth after reboot. Await physical-action clarification before next experiment.
Root sourceworker494498 remains idle with no request03; deadline~00:48. Details:
results/2026-10-16/fresh-card-input-diagnosis.md and post-replug-005-* logs.

2026-10-16 00:28 Asia/Taipei: attach003 also FAILED native input init, exit1;
source90s returned normally. No frames/DMA armed. Storagebeforeafter ext4count0/
testhashunchanged. Sourceworker003 is now running with cached local privilege,
rootPID494498, deadline hostmonotonic272337.54 (~00:48); keep its window open.
Used second slot for60s native-init004: independentMMIOobserves lock1 and VTC
enabled0xa, but no valid input; native5s constructor fails. Nativecounter1018
was already frozen before childcall, so do not blame HPD/nativecall as proved.
All source modes stillrequestedVGA; actualEDIDdifferenceunresolved. Helpers have
not fixed capture. Docs/results/2026-10-16/fresh-card-input-diagnosis.md preserves
findings; failedattach003 rawresults remain in2026-10-15. Asked physicalPCUSB-C
adapter replug; watcher session59292 logs artifacts/operator/usb-replug-005,
await disconnect/reconnect. No request03 queued and no sender currently active.
After Done: inspect watcher/EDID/connector identity, verify current Halted before
any new load, then use remaining sourceworker slots without another PCsudo if
still alive. Never weaken geometry/pixel/integrity checks to force a pass.

2026-10-16 00:14 Asia/Taipei: user requested retry again. No source-session
ready/run outputs exist, no sender is running, and the previous auth window
has ended. Fresh board sudo-n-v requires a password. Reopened one local
terminal PYNQ retry - board then PC using retry-kms-source-session.sh: board
sudo-v/miniterm exit, immediate noninteractive verification, then local PCsudo
and the existing bounded source worker. The queued90s run and coordinator
session82445 remain pending; no hardware capture has started. Do not contend
UART while the operator miniterm is open. Evidence:
artifacts/operator/new-card-attach-003-retry-preflight.log.

Timing002 completed:75 source flips, exit0, originalVT restored. Kernel DRM
snapshot now captured successfully: test planeXR24/640x480, CRTC mode25200kHz/
800x525 totals; no adjusted_mode field or physical wire-format proof. Actual
board nativeVSYNC623→683→743 (120 in2.003853s,~59.885Hz), but invalid_frames
also+120 while gate disabled/selected0/DMAHalted. No capture/qualification pass.
Prepared operator-only attached-source contrast using original capture checks,
current verified017/reset0command and no FPGA reload. New runtime variant is
explicitly experimental. Attach003 coordinator session82445 waits up to30minutes for
artifacts/operator/kms-source-session-003/run-01. Local bounded source worker
terminal opened: one PCsudo auth, first90s source queued; fixedVT3/output,
max6runs/30min. Five request-parser cases pass; root/session execution pending.
No production capture adapter changes yet. Preserve failed001 and timing002.

KMS001 source has now returned normally:2700 page flips, childexit0,
originalVT2 restored. Capture still failed before any frames; source success
is not capture success. Post-run scaling mode=None and link-statusGood;
GPU upscaling is not established. New20s timing probe prepared and local host
sudo terminal opened. The VT runner now records bounded kernel DRM metadata
after source readiness; py_compile passes, actual diagnostic execution pending.
Timing source dir:artifacts/operator/kms-vt-newcard-timing-002; watcher session
59012 waits for ready then samples board MMIO, without starting DMA.

Fresh-card KMS001 failed before frames: KMS ready XR24/640x480/25200kHz,
sender then timed out in native frontend.configure and exited1. No smoke or
600s qualifier ran. Coordinator shutdown_safe=null remains original; resource
log fetch failed because no resource sampler was launched. Supervisor before/
after storage checks pass, ext4count0/hash unchanged. Later raw S2MM RS0/Halted1,
gate disabled/selected0/completed0 establish current stopped hardware state.
HPD one-second pulse did not resume nativeVSYNC counts. Clocks match100/
142.857143/200MHz, SLCR reset0. KMS source remains bounded720s and will return
VT2; wait for restore.json before another source run. Host connector scaling/
adjusted timing remains to inspect after DRM access returns. Do not claim a
new-card capture pass. See new-card-hdmi-startup-report.md and failed KMS001
coordinator/logs. No sender is running; no capture pool was allocated.

2026-10-15 23:35 Asia/Taipei: first fresh-card frontend preload FAILED.
Actual sudo succeeded but configure waited for unsupported4K desktop video and
reported no input. Host-visible DGL EDID differs from builtVGA EDID, including
4K DTD; origin unresolved. No sender/DMA started; raw CR0x10002/SR0x10001.
Revised one-run HPD-only attach passed on board without waiting for lock or
allocating capture buffers. Keep gate disabled and DMA Halted until directKMS
VGA is ready. Original failed preload and EDID/Mutter/MMIO evidence retained in
[new startup report](results/2026-10-15/new-card-hdmi-startup-report.md).
Coordinator is waiting for new source readiness. Opened a local terminal
PYNQ KMS - PC sudo only; board auth currently valid, only host VT sudo needed.
The old full wizard remains failed; do not rerun/reuse its evidence paths.
Newcard sustained capture/cleanup and EDID cause still unverified.

2026-10-15 23:22 Asia/Taipei: retry preflight confirms same board boot ID,
ext4 errors_count0, no sender/supervisor processes, and no existing new-card
KMS/preload/coordinator evidence. Board sudo and host sudo both still require
interactive authentication. No overlay/capture retry was sent by this probe.
Opened a local Ptyxis terminal titled PYNQ capture retry, waiting for the
operator to press Enter and start the prepared wizard. No password is read by
the launcher; passwords go only to local sudo prompts. The terminal launch
command returned0, but operator interaction/test execution is not yet confirmed.

Fresh-card capture replay PREPARED, NOT RUN (after storage pass).
Unchanged sender-v10 and overlay017 archives copied to
`/tmp/hdmi-capture-newcard-017-v10`; archives and paired bit/HWH hashes match.
Fresh board PYNQ3.0.1/NumPy1.21.5 import passes. Dedicated NIC profile restored;
2/2 scoped IPv6 pings pass. PC DP-2 currently disconnected with empty EDID.
Prepared frontend-only preload with gate disabled and halted VDMA, followed by
connected-DGL EDID verification before KMS. No pixel-validation relaxation.
One operator command `bash artifacts/operator/new-card-kms-test.sh` handles
local board auth, preload, host VT auth and fresh720s KMS/600s qualification.
The root board supervisor waits for the sender's650s native timer; it never
kills a DMA child on timeout. It saves kernel/storage checks after normal exit.
This removes the need for cached sudo at the end of the long run. Failure to
obtain a final safety result remains UNKNOWN and forbids another overlay load.
Static Bash/Python checks pass; complete wrapper is NOT RUN. Actual board
sudo-n-v requires a password after reboot; operator execution requested.
`new-card-capture-preparation.json` records helper hashes and remaining checks.

2026-10-15 23:09 Asia/Taipei: new-card normal REBOOT/PERSISTENCE PASSED.
Operator wrapper completed at23:07:03: 49.202s normal reboot, changed boot ID,
16,777,216-byte file retained with expected SHA256. All evidence hashes match.
Full privileged pre-reboot dmesg and shutdown/new-boot UART saved. Post-reboot
ext4 errors_count=0; no old block/EXT4 I/O errors observed in captured logs.
SD high-speed warning persists: measured actual25MHz,4-bit,legacy timing.
DHCP units still failed; do not claim fully clean OS or complete media health.
No capture overlay/sender loaded yet. Resume unchanged017/v10 staging and fresh
capture+safe-cleanup validation; fullM1 remains incomplete. See
[storage result](results/2026-10-15/new-card-storage-report.md).

2026-10-15 23:04 Asia/Taipei: full SD diagnostics/reboot still PENDING.
After the user's Done, a fresh UART `sudo -n -v` returned password required;
no reboot command was sent. The failure is preserved in
`results/2026-10-15/new-card-auth-expired.log`. Prepared an operator wrapper:
`bash artifacts/operator/new-card-storage-check.sh`. It opens the existing
UART authentication wizard, then immediately runs diagnostics, one normal
reboot and the persisted 16 MiB file check after miniterm exits. This avoids
the chat round trip before use of the sudo cache. Any failed step stops the
sequence; existing evidence prevents a repeat or overwrite. Bash syntax and
Python compilation passed; the complete operator sequence is NOT RUN.
No capture overlay/sender deployed yet. User authentication is pending.

2026-10-15 22:58 Asia/Taipei: fresh-card FIRST BOOT PASSED.
PYNQ 3.0.1, Python 3.10.4, Linux 5.15.19. Root expanded to 57 GiB with about
49 GiB free. Card serial/capacity match the new SD. Commands and imports work;
no recurrence of old EXT4 I/O errors in the captured evidence. Dedicated IPv6
profile restored and 2/2 pings passed. Retain warnings: mmc high-speed switch,
haveged SIGSYS/restart limit, failed DHCP servers and journal ACL lookup.
16 MiB test file+directory fsynced; persistence after reboot NOT yet checked.
Sudo authentication required for full diagnostics/reboot; requested local auth.
Do not claim full storage/M1 qualification. See
[first boot](results/2026-10-15/new-card-first-boot-report.md).

2026-10-15 22:47 Asia/Taipei: NEW CARD READBACK PASSED.
The verify-only helper read all 7,858,807,808 bytes in 94.805 seconds. The SHA256
matches the official PYNQ-Z2 v3.0.1 image. It wrote zero bytes. The original
uutils dd zero-byte failure is retained. No second flash occurred. New card
is unmounted/RO on the PC, ready for a powered-off move to PYNQ and first boot.
Old card and complete backup remain preserved. Boot/storage/clean-shutdown
checks and the remaining M1 recovery tests are still pending. Evidence:
[new card verified](results/2026-10-15/new-card-readback-verified.json).

2026-10-15 22:43 Asia/Taipei — old-card backup COMPLETE:15,978,201,088B,
all rescued/0readerrors. FATdirty(exit1),ext4errors(exit4) with journal skipped;
no physical fault proved, preserve original/image. User flashed newmmcblk0:
7,858,807,808B written, original readback failed0bytes dueuutilsdd0.8 direct-I/O
path (same failure reproduced on localimage). Native4096-alignedpreadO_DIRECT
reads full localimage with expectedSHA;7 direct-filetests pass. Verification-only
helper prepared; waiting local sudo raw-card verification, do NOT rewrite or
boot until verified. See[diagnosis](results/2026-10-15/sd-readback-diagnosis.md).

2026-10-15 22:25 Asia/Taipei — readonly old-card rescue now ACTIVE after
lsblk--tree correction. Source sdb/sdb1/sdb2 allRO=1, no raw writes. At~7m35s,
8,174MB/51.16% recovered with0 read errors; rate fell from~50MB/s to variable
sub-MB/s near8GB. Partial image/map underartifacts/sd-recovery/old-card-backup-001;
no finalreport or filesystem checks yet. Sub-agent updated audit; no hardware
health verdict. New-card flasher preparation passed and source reviewed;
explicit overwrite consent/local execution still pending. New card untouched.

2026-10-15 22:17 Asia/Taipei — user inserted new SD asmmcblk0 (SD64G,
CID9f544953443634476194980972018201,58.3GiB) and old PYNQ SD assdb
(14.9GiB, knownPYNQ/root UUIDs). Old boot partition unmounted, root unmounted.
User requested fresh official image plus sub-agent old-card audit. Official
v3.0.1 archive downloaded/extracted withCRC+SHA checks; preserves tested runtime
baseline. New-card dry preparation verified; NO FLASH YET, explicit target
consent pending. Old-card raw backup/check needs local sudo. First helper run
safely rejected flatlsblk JSON;--tree fixed and actual identities passed. Waiting
operator retry; no backup/health verdict yet. Sub-agent initial audit finds FAT
unclean warning, no host I/O errors yet, cannot certify media. See
[SD recovery](sd-recovery.md) and[old-card audit](results/2026-10-15/old-sd-audit.md).

2026-10-15 21:55 Asia/Taipei — KMS/017/v10 strict600s capture PASSED:
1201/1201 exact RGB frames in600.155270s (2.001149FPS), zero pixel/mixed/repeat/
metadata/transport/storage failures. Native accounting36000=1200+34800;
all1201 optical IDs matched KMS records. Source completed720s/2700flips and
returnedVT2, exit0. HOWEVER cooperative shutdown could not execute sudo due
EXT4/mmcblk0p2 I/O errors. ps/tail also fail. Builtin rescue recovered resources
and sender fatalSIGBUS trace; /proc/16610 absent, DMA safetyUNKNOWN. Do not load
another overlay or claim fullM1. No SD repair attempted. Preserve evidence and
recover hardware/storage before interruption testing. See
[full report](results/2026-10-15/m1-017-kms-001-report.md).

2026-10-15 21:29 Asia/Taipei — direct KMS source probe002 passed: VT3,
XR24/640x480p60 (25200kHz),37 completed page flips, exit0, returnVT2 verified.
Omitted --vt is correct because default is3. This is source-only proof, not
board RGB qualification. Board has no sender and sudo authentication expired
(actual sudo -n requires password). Preparing source/overlay/receiver coordination
for real KMS-input capture. Evidence:[probe002](results/2026-10-15/kms-vt-probe-002.json).

2026-10-15 21:16 Asia/Taipei — first operator direct-VT probe returned toVT2
but source failed DRM-master acquisition. openvt pickedVT1, starting a GDM
greeter compositor (sessionc2/tty1). Runner now explicitly targets unusedVT3,
rejects occupied session VTs, and logs actual VT/session state. Revised local
sudo probe pending; source never produced a frame in the first VT test.

2026-10-15 21:09 Asia/Taipei — user requested HDMI source outside GNOME.
Notification suppression failed600s (1148/1201 exact); settings restored.
10-bit analytic GLES prototype passed15/15 with notifications but remains only
an isolated experiment. A DRM-lease prototype produced18 page flips then crashed
GNOME50.1 during revoke; main desktop restarted. No further lease retries.
DP-2 restored59.940, main monitor unchanged, banners=true. Board bounded sender
exited safely. Direct KMS C source and temporary-VT runner are built;9 source
tests pass, active-desktop master acquisition refuses safely. Direct-VT live
output/return remains unverified and needs local sudo. See[kms-source](kms-source.md).

2026-10-15 20:44 Asia/Taipei — frame difference reproduced and isolated to a
notification-triggered source-presentation failure mode. The first017 ten-minute
run failed (1189/1200 exact;7 one-LSB cases and4 damaged-marker cases). Fixed-ID
real-board notification regression: banners suppressed15/15 exact; enabled10/15
fail. No FPGA/capture tolerance changed. User authorized temporary suppression;
15-minute restore timer armed. Animated600s rerun `m1-017-v10-dnd` is active;
board PID11749, resource sampler11880. Diagnosis and limitations:
[frame difference](results/2026-10-15/frame-difference-diagnosis.md).

2026-10-15 20:27 Asia/Taipei — build017/v10 first real RGB capture passed:
11 distinct exact640x480 frames in5.399744s, zero pixel/mixed/repeat/metadata/
transport errors. Raw DMA0x11001 auto-halted, held IDs and sampling arithmetic
validated300native intervals=10acquisitions+290skips. Short-run evidence only;
ten-minute and interruption tests still required. Local source fix34e35dd.

017 CAD exit0: setup/hold0.401/0.014ns,56skewMET,0criticalCDC/DRC;256Gray+6reset
ASYNC_REG confirmed. Fresh HLS and actual exported RTL pass exact drain/stall
checks. Paired artifact hashes matched on board at
`/tmp/hdmi-capture-credit-017-v10/overlay-017`. Source PYTHONPATH is its parent.
Cooperative smoke shutdown halted safely before free; one selected-completed
frame was cancelled before acquisition commit at the boundary (101vs100),
outside the explicitly reconciled delivered window. UIO destructor warning retained.

New900-second sender launched for sustained qualification; startup PID10326 is
sudo, find the actual Python child before resource sampling or signaling. No
other sender remained at launch. Source/DRM fixture from20:17 stays active.
Next: wait listening, start600-second/600frame qualifier with resource samples,
then client pause/reconnect, mode and physical unplug/recovery. See
[smoke](results/2026-10-15/m1-017-smoke.md) and
[CAD](results/2026-10-15/credit-017-build.md).

2026-10-15 20:22 Asia/Taipei — current candidate017 is building from frozen
`artifacts/m1-project-017-source`; shell handle30743, console
`artifacts/m1-project-017-console.log`. Fresh HLS and four exact generated-RTL
drain cases passed; Vivado IP synthesis is running. No017 board capture yet.
Implementation commit34e35dd fixes the isolated copied color pipeline with
style=flp; original016 reproduces the five-pixel stall. Ordinary308tests pass
with one optional skip. Strict DMA/timing/CDC/DRC checks remain enabled.

The PC is unlocked with active640x480p59.94 animated GLES output. Bounded source
and read-only DRM logs use `artifacts/operator/m1-017-*` (2400seconds from20:17).
V10 source and resource sampler are hash-verified at
`/tmp/hdmi-capture-credit-017-v10`;017 overlay transfer waits for accepted CAD.
No board sender is running. Sudo refreshed noninteractively at20:20 while valid.
After strict build success, pair017 with this unchanged v10 source, run a short
exactRGB/accounting smoke, then600seconds/600newframes and interruption tests.

2026-10-15 20:12 Asia/Taipei — operator resumed with active HDMI and sudo renewed.
016/v10 now configured real input, selected SOF66/native67 and closed one credit,
but VDMA did not complete: zero acquisitions. Safe abort halted before free.
Actual generated-HLS simulation reproduces the cause: color_convert holds five
tail pixels when an isolated selected frame ends; pack-only drains completely.
Candidate repair is a flushable color pipeline with a generated-RTL regression
before fresh CAD. Additional DMA issues remain possible; M1 is incomplete.
See [drain evidence](results/2026-10-15/credit-016-hls-drain.md).

2026-10-15 09:22 Asia/Taipei — current candidate is build016 plus sender v10.
M1 remains incomplete. Build016 passed CAD with setup/hold0.399/0.033ns,
56 bus-skew checks MET, zero criticalCDC/DRC and verified synchronizer attributes.
Latest software tests:308 passed,1optional-dependency skip; dedicated gate/manifest:
64 passed. These local checks do not establish successful new physical capture.

The board-loaded016/v9 attempt acquired zero frames: PC ScreenSaver=true,
PowerSaveMode3 and inactive DRM DP-2 caused no incoming HDMI signal. Latest
read-only recheck still shows the desktop locked/output off, board alive and
no capture process. All CAD, shader and scanout processes have terminated.
User wake/unlock and replyDone are pending; HDMI should remain connected.
Do not restart capture until actual scanout is active. Existing overlay/network
permission persists; credential availability must be rechecked separately.

Use source PYTHONPATH `/tmp/hdmi-capture-credit-016-v10` with paired files at
`/tmp/hdmi-capture-credit-016/overlay-016/{capture.bit,capture.hwh,build-manifest.json}`.
Both package transfers matched SHA256. Current local commits include359ba31,
0390bb9 and53e23a9. Source/counter diagnostics and cleanup preserve known errors;
formal qualification requires clean source and cleanup counters. No images uploaded.

Next authorized actions: confirm active640x480p59.94/60 source, restart animated
GLES fixture with contemporaneous scanout logs, recheck sudo, run short smoke
requiring DMA autoHALT+IRQ and next-SOF-closed held identity with exactRGB. Only
then run600-second/600-new-frame qualification, client reconnect, source unplug
and mode-change recovery tests. No web/bypass/LCD work is started.

Evidence: [016build](results/2026-10-15/credit-016-build.md),
[diagnostic tests](results/2026-10-15/credit-fault-reporting.md),
[failed015timing](results/2026-10-15/credit-015-timing.md).

## Credit bring-up history

2026-10-15 — Build014 single-credit implementation and local checks completed;
first physical smoke failed automatic DMA halt; continued investigation required. Do not mark M1 complete. See
[the new checkpoint](results/2026-10-15/credit-014-build.md) for artifacts,
behavioral impact, 291 software tests and 62 gate/manifest tests. The new producer
is `--source litex-credit`; legacy013 requires `--source litex` and the qualifier's
explicit `--legacy-delivered-image-criterion`. Source accounting cannot be inferred
from old continuous-ring counts.

Build014 bit/HWH/manifest and v6 deployment packages are ready. Latest UART
preflight is `artifacts/operator/credit-ready-preflight.log`; sudo authentication
must be rechecked/renewed locally before board load. The first sender exited safely after a read timeout; no active DMA remains.
The optical fixture has a bounded duration and must be rechecked before use. User physical-unplug availability remains pending; never ask
them to unplug until a new capture is running. Subagents hit usage limits;
parent resumed direct checks and finished the local checkpoint.

[First build014 board attempt](results/2026-10-15/m1-014-bringup.md) records
zero delivered frames, safe halt-before-free, and the qualifier integration fix.

Build015 failed strict timing and was rejected. Build016 then passed CAD
(setup/hold0.399/0.033ns,56skewMET, no criticalCDC/DRC) and was board-loaded with
v9. Its first configuration found no HDMI signal because the PC screen was
locked/powered off (ScreenSaver=true, PowerSaveMode3; DRM DP-2 inactive). Sender
exited before DMA allocation/start; no hardware sender or fixture is active.
The user has been asked to wake/unlock the PC and replyDone, leaving HDMI connected.
This real source prerequisite is pending; don't reask overlay permission.
See [016checkpoint](results/2026-10-15/credit-016-build.md) and
[timing investigation](results/2026-10-15/credit-015-timing.md).
The paired016 artifacts and v9 package are transferred, with matching hashes.
V10 is the current source package, including truthful failure/cleanup counts;
it is transferred with matching SHA256 to `/tmp/hdmi-capture-credit-016-v10`.
Use that PYTHONPATH with the paired bit/HWH in
`/tmp/hdmi-capture-credit-016/overlay-016` for the next run. [Diagnostic evidence](results/2026-10-15/credit-fault-reporting.md)
records308 passing tests and1optional skip.
Next: verify source output active after operator reply, restart animated fixture,
run bounded smoke requiring autoHALT/IRQ plus held frame identity and exactRGB,
then renewed600-second run and physical/interruption tests. Sudo was noninteractively
refreshed at08:38 while valid, but may have expired during the operator wait;
recheck before restart. No images were uploaded.

## Preserved previous checkpoint


2026-10-15 Asia/Taipei — real LiteX HDMI capture sustained criterion passed;
source accounting and physical cable-removal qualification remain incomplete. User explicitly requests incremental
local commits as progress is verified; no push is authorized.

## Working path and evidence

PC USB-C/HDMI adapter → PYNQ-Z2 HDMI IN → LiteX gate → VDMA/PS DDR → PS Ethernet
→ Python uint8 RGB888 works at 640×480p60. Build013 and sender v5 delivered
1,201 distinct exact optical frames in 600.505782 seconds, 1.999981 FPS and
14.745458 Mbps. Zero bad/mixed/repeated frames, metadata/transport errors or new
invalid/FIFO events. Startup invalid=1 is explicitly attributed to unselected
input using a held-disabled baseline, not erased. Physical source sequence and
DDR-ring overwrite attribution remain unknown.

[Qualification report](results/2026-10-15/m1-qualification.md) contains evidence,
limits, counters, resource use and timing. [Bring-up](results/2026-10-15/m1-bringup.md)
preserves rejected attempts; [M0 history](results/2026-10-15/m0-bringup.md) retains
the unresolved earlier kernel panic and +1LSB source failures.

Gate half-second off/on counted30 dropped frames and resumed selection. Client
pause8seconds/reconnect passed6 exact distinct frames with13 backpressure drops.
Changing60→59.94Hz correctly stopped the sender during relock; DMA halted before
five buffer frees. Explicit restart recovered10 exact frames at59.94Hz. Automatic
mode recovery is not implemented. Existing UIO destructor warning remains.

Local integrated tests:195 passed,1 optional-dependency skip. Dedicated gateware:
17 passed,0skips. Build013 setup/hold0.516/0.020ns, all41bus-skewchecks MET, no
critical CDC/DRC or internal unconstrained endpoints; remaining warnings, external
I/O gaps, vendor waivers and startup simulation diagnostics are documented.

## Current operator step and runtime

The bounded recovery sender PID13150 exited normally after 600 seconds. Its
log confirms VDMA Halted before all five buffers were released, with
`dma_shutdown_safe=true`; the board remained alive. The source renderer and
scanout logger also exited with status zero. Evidence:
`results/2026-10-15/m1-recovery-duration-check.log`. The existing UIO destructor
warning occurred after safe cleanup. No current sender or pattern is armed.

The user was subsequently asked to reply when available, and to leave the cable
connected until a new test is armed. Physical removal has not been confirmed.
Do not reload an overlay or kill a process while DMA may be active. Cooperative
SIGTERM is handled; background nohup SIGINT was ignored. Confirm Halted before
buffer release. If native stop cannot complete, retain process/BOs and recover
physical hardware; never add forced SIGKILL. Recheck actual runtime before use.

Completion audit found an unmet P4 requirement: global PL counters and software
read IDs do not associate source frames with individual DMA buffers. The
36,000 selected / 32,359 acquired endpoint deltas cannot establish 3,641 overruns.
The delivered pixel test passed, but physical source skips and ring overwrite
counts remain unknown. A single-credit gate and fixed-slot one-frame VDMA reader are now being
implemented. Completion requires gate end-of-frame plus VDMA auto-Halted;
frame-count IRQ alone occurs at transfer start and is insufficient. Source ID
remains stable through the software copy/lease. Native VSYNC versus AXI SOF
tracking must distinguish lost input from intentional unselected frames. This is required M1 work, not an optional later enhancement.

Board UART is `/dev/serial/by-id/usb-Xilinx_TUL_1234-tul-if01-port0`,115200.
`tools/board_console.py` uses the already-authenticated session; sudo was renewed
locally after reset, but the latest read-only preflight now reports its
credential cache expired (`artifacts/operator/credit-preflight.log`). Board is
alive and no sender was found. Renew authentication only when the next board
experiment is ready, to avoid another idle expiry. No passwords belong in chat. Board link-local address is
`fe80::200:5ff:fe6b:1a0%enx98fc84e0c4e8` on this host. Temporary dedicated NM profile
`codex-hdmi-m0` remains active; prior connection UUID
`864ebd1d-48cd-3cc5-bddd-93475bb4700e` is saved. Temporary display snapshots are in
ignored `artifacts/operator/`. Restore only after pending hardware testing and
verified safe sender cleanup. No SD repair/reimage or global package change.

## Reproduction and scope

[Quickstart](quickstart.md), [build](build.md), [sender](board-capture.md),
[protocol](protocol.md) and [qualification](qualification.md) document setup.
Build013 artifacts are `artifacts/m1-project-013/{capture.bit,capture.hwh,build-manifest.json}`.
Rebuild scripts pin vendor/RTL dependencies. An isolated clean-checkout replay of `aa4e86e` completed with fresh pinned RTL,
both HLS packages and bitstream in `artifacts/clean-replay-001`. Setup/hold margins
are 0.568/0.017 ns; all 41 bus-skew checks pass, with no critical CDC/DRC or
internal unconstrained endpoints. Retained warnings and source hashes are in
[the clean-build report](results/2026-10-15/clean-build-report.md). This proves
legacy-path reproducibility, not on-board qualification of the newly built
artifact or the pending source-accounting changes. Build013 itself reused HLS
outputs generated locally in001. Real arrays remain in
ignored artifacts and were not uploaded. Web/bypass/LCD remain deferred.

User already confirmed640×480p≈60RGB888,>=1freshFPS for10minutes/>=600frames,
counted whole software drops, PS Linux TCP path, and temporary overlay/dedicated
network operations. Do not repeat first-round approval questions. The source is
this PC's verified USB-C→HDMI adapter and cable. See requirements for decisions.
