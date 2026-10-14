# PYNQ-Z2 + LiteX HDMI Capture — Implementation Prompt

你是這個專案的 Embedded / FPGA / Host Software 工程師。請在目前工作目錄中實際研究、修改程式、建立測試並推進實板驗證，不要只提供架構建議。

使用繁體中文與我討論，程式識別字、註解和 API 文件使用清楚、直接的英文。技術說明依「目標 → 原因 → 指令／實驗 → 一句話結論」呈現；提供可核對的設計理由，不要輸出冗長內在思考。

## 1. 已確定的需求：不要重新詢問

硬體是 PYNQ-Z2，專案要使用 LiteX。已有兩片 LCD：Waveshare 3.5inch RPi LCD (A) 與 (C)。

需求如下：

1. **最高優先：PC Host 使用 Python，經 Ethernet 擷取 PYNQ-Z2 HDMI Input 的真實影像。**
2. 瀏覽器可以連上去觀看 HDMI Capture 畫面。
3. HDMI Input → HDMI Output Active Bypass，只需要轉送畫面，不需要影像處理。
4. 擷取主線重點是 RGB 4:4:4，不能靠色度次取樣或有損壓縮偷換需求。
5. 未來把畫面縮放後顯示到上述其中一片 LCD。首個 porting target 選 **3.5inch RPi LCD (C)**；除非取得明確相反證據，不要同時開發兩款。

第 1 項先交付。網頁、bypass、LCD 都不能成為開始實作擷取的前置依賴；但最初的架構需避免未來加入它們時重寫整個資料路徑。

以下是需要在 grill 階段確認的「建議預設值」，不是使用者已確認的事實：

- RGB 4:4:4 先定義為每色 8 bits 的 RGB888／24 bits per pixel，不是每色 4 bits 的 RGB444 packed format。
- MVP：HDMI 輸入 640×480 progressive、約 60 Hz；PC 先穩定取得至少 1 個完整新 frame/s。之後才擴充 1280×720p60 與更高擷取率。輸入更新率與 PC 擷取率分開定義。
- 首版採 raw RGB888 over TCP；PC Python 不必被作業系統辨識成 USB/UVC capture device。
- 允許 Zynq PS 跑既有 Linux/PYNQ 環境，以 PS Ethernet 搬資料；LiteX 負責實際參與擷取的 PL 邏輯。不要預設一定要加 soft CPU。
- 網頁的最終使用方式預設是連 PYNQ-Z2 的 IP，不是必須另外啟動 PC relay。
- 「ISP Driver 的 LCD」暫解讀為「SPI LCD driver」；把這個用詞差異列入確認，不自行展開完整 ISP pipeline。
- 首版只處理未加密、8-bit RGB progressive video。不包含 HDCP、音訊、CEC、HDR、deep color、interlace 或完整 HDMI repeater 認證。

## 2. 先執行 grill-with-docs，再進入 implementation

先檢查目前 repo 的 AGENTS.md、README、既有設計文件、git status 和已安裝技能。

載入並遵循三個技能：

- grill-with-docs
- grilling
- domain-modeling

Codex 相容性要求：

- 不要假設環境存在名為 Skill 的工具。沒有該工具時，直接讀取這三個技能的 SKILL.md，並讀取 domain-modeling 引用的必要格式檔。
- 優先使用目前環境列出的技能路徑；再檢查 repo 的 .agents/skills 與 ~/.agents/skills。不要假設我已安裝。
- 若本機缺少，可讀取下方 mattpocock/skills 官方 repo 的檔案，將三個技能及所需格式檔固定在同一個 commit。不要為此覆寫全域設定或執行未審查的安裝腳本。
- 回報實際讀到的路徑／版本。若無法取得原技能，明確說明，仍依本節內嵌流程執行；不得宣稱已載入不存在的技能。

訪談規則：

1. 先由 repo、官方文件、程式和本機探測回答技術事實；只有使用者偏好、驗收取捨和無法自行取得的實體資訊才問我。
2. 每輪最多問 3 個真正阻塞當前里程碑的問題；尚依賴未決答案的問題留到下一輪。不要先追問 LCD 觸控等未來細節。
3. 每題包含「要決定什麼、目前證據、你的建議、選擇的影響」。讓我可以直接回答「同意建議」。
4. 等我回答再進下一輪。沒有回答不代表同意；不得把本 Prompt 的建議預設值記成已核准。
5. 對術語與情境提出具體挑戰，例如：PC 收得慢時可否丟整幀？拔掉 Ethernet 後 bypass 是否要持續？RGB 資料的位元組順序與量化範圍如何驗收？
6. 已確定的需求、我先前回答過的問題，不得重問。發現文件與程式矛盾時，提出矛盾與證據。
7. 當前里程碑已收斂後，摘要請我確認共同理解；確認後直接實作該里程碑，不要每個小修改都重新訪談。後續里程碑再做必要的局部 grill。

文件必須真的寫入 repo，不只出現在聊天：

- GLOSSARY.md：術語一確定就更新，只放定義，不混入規格或實作筆記。
- docs/requirements.md：保存所有需求、數值、禁止事項、已回答問題與選項，區分 confirmed / proposed / observed。
- docs/adr/：只為難以逆轉、缺乏背景會令人意外、且存在真實取捨的決策建立 ADR，不為每個小決定製造文件。
- docs/research.md：來源、版本／commit、相關檔案與行號或 PDF 頁碼、結論、尚未驗證的部分。
- docs/progress.md：目前可工作的路徑、已執行指令、證據、阻塞與下一步。

沿用 repo 既有等價結構，不另造重複文件系統。一般決策即使不夠資格成為 ADR，也必須留在 requirements 中；不能只存在聊天。重要需求要能追溯到程式與驗收測試。

## 3. Architecture feasibility gate：先查證，不編造支援

先做範圍受限的環境與程式盤點：

- 現有 LiteX、litex-boards、Migen、PYNQ、HDMI IP、DMA、Ethernet、Host Python 實作與版本。
- Vivado 版本、可用 IP 與授權、build scripts、Python 環境、實板連線方式。
- 從既有設定尋找 board IP／SSH／serial；找不到才詢問，不要求把密碼或私鑰貼進聊天。
- 目前工作樹是否有未提交修改；保留使用者工作，不任意重建 repo。

必查的硬體事實：

1. PYNQ-Z2 的板載 Ethernet PHY 接在哪裡、PS GEM/MIO 與 PL 的界線。不可把板載 RJ45 畫成 LiteEth 可以直接驅動的 PL PHY。
2. HDMI RX/TX pins、DDC/HPD、clocking、電壓／IOSTANDARD 與 board revision；從 PYNQ-Z2 原理圖、官方 constraints 和已驗證設計交叉確認，不套用 PYNQ-Z1 的 pinout。
3. 實際 DDR 配置、PS preset、AXI HP/GP 接法與 cache coherency；不可把 generic PS7 宣告當成板級記憶體設定。
4. 所有必要時鐘的來源；特別查清板上 125 MHz 時鐘與 Ethernet PHY／link 狀態的關係，避免網路線拔除造成其他功能失鎖。
5. 目前 upstream tul_pynq_z2 target/platform 到底已實作什麼。若只有基本 SoC，或 zynq7000 路徑仍未完成，就列出缺口；不能虛構 --with-hdmi-in／--with-ethernet 等已可用選項。
6. HDMI 模式是否真的有板級依據；不預設 1080p60 可達成正式規格與穩定時序。

來源以官方 board 文件、PYNQ、LiteX upstream、實際 HDL/IP 原始碼與授權為準。搜尋結果標題不是相容性證明。PDF 涉及 pin 表或圖時，讀對應頁面，而非只憑文字片段猜。

提出一個推薦架構，說明 LiteX、Vivado/IP、PS 軟體各負責哪些功能及整合成本。候選主線是：

HDMI RX → LiteX capture logic → frame DMA/VDMA → PS DDR
        → PS sender → onboard Ethernet → PC Python RGB frames

另保留不互相阻塞的 consumer：

- HDMI RX → video forwarding path → HDMI TX
- 已完成 frame → web preview
- 已完成 frame → future scaler → LCD pixel conversion → SPI LCD

LiteX 可以作為無 soft CPU 的 PL 子系統，與既有 PS/Linux 整合。HDMI front-end、DMA 可以重用可取得、可重建的現有 IP，不必為了「全 LiteX」重寫成熟模組。

但正式 LiteX milestone 必須有 LiteX 產生的邏輯實際參與 capture，例如 frame gating／capture control 與對應統計，不得只 import LiteX、掛一個無關 LED，或把純 PYNQ demo 改名。

## 4. 實作里程碑：先提供可用擷取，再擴充

### M0：最短路徑建立真實 baseline

在具備實板與適當授權時：

- 用既有可工作 overlay／HDMI front-end，確認真實 HDMI source 可擷取到 PS DDR。
- 分開測量 PS ↔ PC 網路 goodput，以及 synthetic RGB frame 的 PC 接收正確性。
- 儘快提供 PC 可執行的 Python capture client，先看到並保存真實 HDMI frame。

允許 M0 使用 PYNQ base overlay 作 bring-up，但明確標示 baseline-only；這是先交付功能，不代表 LiteX 整合完成。synthetic sender 也不能冒充實際 HDMI Capture。

### M1：LiteX 整合後的正式 PC Capture MVP

- 加入並驗證 LiteX 的 capture 功能，產生可重建 bitstream。
- 完成板端 sender、Host Python library、CLI、原始 frame 保存與測試。
- 在已同意的輸入模式與擷取率下，做長時間實板驗證。
- 第 1 項需求的正式完成證據要覆蓋這條真實 LiteX＋HDMI＋Ethernet 路徑。

### M2：網頁監看

- 重用 M1 的 frame service，不另寫第二套爭用 DMA 的擷取器。
- 先實作簡單頁面、snapshot 與 status，不先引入 WebRTC、H.264 或大型前端框架。
- 預設瀏覽器連板端 IP。PC relay 可作臨時 bring-up，必須標清楚，不能冒稱板上 web server 已完成。
- 頁面顯示解析度、實際 FPS、frame ID、連線狀態與 stale-frame 提示。
- JPEG/MJPEG 只准用在獨立 preview 分支，不能取代主線的無損 RGB 擷取驗收。

### M3：Active Bypass

- 先確認 bypass 的共同定義：首選是同解析度／同更新率、不 scaling、不做色彩轉換的 video forwarding；不是被動導通或 TMDS 電氣直通。
- 不假設它必然等於零延遲。若使用 framebuffer，需揭露 buffering、延遲與 frame repeat/drop 行為，再確認是否符合需求。
- 若採 PYNQ tie() 等 API，先讀實作，不能只憑名稱判定它繞過 DDR。
- 驗證 capture 開／關、PC 暫停讀取、sender crash、Ethernet 斷線時的輸出行為。
- 釐清 DDC/EDID/HPD、input lock、mode change、sink disconnect 的策略。不要把只支援 video 的路徑稱為完整 HDMI repeater。

### M4：未來 LCD，不得延誤 M1

- 首先只留下明確的 frame consumer 介面與移植文件，不提前完成所有 LCD 功能。
- 到此階段才實作 C 款的初始化、純色／色條、frame upload、scaling。
- 首版 scaling 可在 PS 軟體做，先保持 aspect ratio 與 letterbox；有量測瓶頸才搬到 PL。
- LCD 分支可以 RGB888 → RGB565 等格式轉換，不能降低 Host capture 的色彩精度。
- 參考 Waveshare 與 Radxa 的公開實作，但核對使用者實際板款／revision；不能把 Raspberry Pi 專用 overlay／LCD-show 安裝腳本直接在 PYNQ 系統執行。
- 確认 controller、初始化序列、SPI transaction packing、D/C、CS、RESET、供電與 pin mapping。不能把「ILI9486」名稱當成所有模組 serial protocol 都相同。
- 從保守 SPI clock 起測，不把 C 款標示的高速能力視為 PYNQ 接線下已保證的速度。觸控不在首版範圍。

## 5. RGB 與影格完整性契約

主線 Host API 對外輸出：numpy.ndarray、dtype uint8、shape (height, width, 3)、順序 R/G/B、每 pixel 三個 bytes。

內部可用 BGR 或有 padding 的 DMA buffer，但必須明確記錄並在 API 邊界正確轉換。不可把 OpenCV BGR、RGBA、RGB565 或經 JPEG 解碼的影像默認成原始 RGB888。

不得默默做 scaling、gamma、limited/full-range conversion 或 YCbCr 轉換。記錄來源色彩格式與量化範圍；無法取得時標示 unknown，不能由 dtype 猜測。首版可限制 source 明確輸出 RGB。

每個交給 Host 的 frame 必須來自單一完整來源影格，不可混幀、撕裂、重用正在被 DMA 改寫的 buffer，也不可用舊 frame 冒充新的 capture。

設計並測試：

- frame buffer ownership／lifetime，至少能區分 filling、ready、sending、free。
- DMA completion、cache invalidate/flush 或相應一致性機制。
- frame ID 與時間戳的實際取樣點；來源時鐘與 Host monotonic clock 不可直接相減冒稱單向延遲。
- intentional sampling、overrun、network backpressure、invalid frame、delivered frame 各自的計數。
- 斷線、停止、重啟與輸入模式改變時的清理與 resynchronization。

HDMI 輸入不能被 TCP 的背壓停止。資料送不及時以明確政策丟棄完整 frame，不能回壓到不可停止的 HDMI source，也不能讓 capture 分支拖停 bypass。

處理正確的 clock-domain crossing 與 reset synchronization。核對 AXI4-Stream Video 的 SOF/EOL 語意，不能把每行 TLAST 誤認成整幀結束；LiteX stream 與 video IP 間的 adapter 必須測試。

## 6. Ethernet protocol 與 PC Python 介面

先選最小可驗證方案：單一 capture client、TCP、raw RGB888、bounded buffering；之後才優化零拷貝或多 client。

協定需要有 framing、version、大小限制與可測試 parser。固定前綴＋有界 metadata＋payload 是可接受的簡單設計，不要靠一次 recv() 就拿到一幀的假設。

至少傳遞：

- magic / protocol version、metadata length、payload length
- width、height、pixel format、row stride／wire packing
- frame ID、timestamp 與其 clock domain／取樣點、必要 flags
- payload checksum，例如 CRC32，用來偵測程式路徑與buffer完整性問題；不是安全認證

固定 byte order、最大合法長度、timeout、EOF、模式切換與錯誤後的重連行為。畸形長度不得觸發無界記憶體配置。處理 partial read、partial write、TCP 合併／拆分與 client 中斷。

PC 端提供一致且可安裝的套件、最小 Python example 與 CLI，至少支援：

- connect / read / close 或等價 context-manager API
- frame RGB array 與 metadata
- snapshot：保存無損原始資料或 .npy，另可保存 PNG
- capture：連續保存 frames 與 metadata
- stats／benchmark：有效 FPS、payload goodput、錯誤與掉幀資訊

OpenCV 僅作選用顯示或操作工具，明確處理 RGB↔BGR。不能以 cv2.VideoCapture(0) 讀 USB camera 取代本專案的網路 HDMI 擷取。

## 7. 效能必須量測，不用 link speed 代替

用腳本產生以下預算與實測表：

bytes_per_frame = width × height × 3
payload_bps = bytes_per_frame × delivered_fps × 8

分清 Mbps、MB/s、MiB/s，並另外計算 packet overhead、DMA stride/alignment、DDR 讀寫次數、buffer copies 與 CPU 負載。

分別量測：

1. PS ↔ PC transport goodput。
2. synthetic sender → PC parser／array／可選存檔速度。
3. HDMI → DDR 的 capture 能力。
4. 真實 HDMI → PC 的端到端有效 FPS。

若輸入 60 Hz、網路只取 1 FPS，查清 DMA 是否仍寫入全部 60 幀，以及是否需要 frame-boundary gating。不能用網路 payload 帶寬替代整個 PL/DDR 預算。

若現有測試速度很低，先找出實際 transport、CPU、buffer size、copy 或 debug bridge 等瓶頸；不得直接把單一測試結果當成板載 Ethernet 的硬上限。

## 8. 測試與完成證據

先取得使用者對數字的確認。建議 M1 驗收基準：已同意的 640×480p60 RGB source、Host ≥1 FPS、連續至少 10 分鐘且至少 600 個完整新來源影格。

在該基準下報告：有效 FPS、corrupt／mixed／invalid frames、intentional skips 與 overrun、CPU／memory、模式資訊、版本與執行指令。收到壞幀即使被偵測，也必須計入結果；不可靜默略過後宣稱零錯誤。

自動化測試至少包含：

- synthetic RGB channel ramps、單 pixel 彩色圖樣、row/column/frame markers，檢查 R/B 交換、次取樣、stride、截斷與混幀。
- 協定拆包／合包／EOF／timeout／畸形長度／checksum mismatch。
- buffer ownership、慢速 consumer、整幀丟棄與重新同步。
- 實際修改的 LiteX/RTL capture 邏輯、video stream adapter、reset 與背壓情境。
- Host API 與 CLI 的無硬體 smoke test。

實板測試要覆蓋：真實 HDMI source、可控制的色條／圖樣、長時間擷取、來源拔插、client 斷線重連、輸入模式變更。無法控制 HDMI source 的像素輸出時，不把 PC screenshot 自動當成 pixel-exact golden reference。

分開標示每種證據：static inspection、unit test、simulation、synthesis、implementation/timing、bitstream generated、on-board verified。simulation 不能證明實體 CDC 安全或板級 HDMI 穩定；產生 bitstream 也不代表實板成功。

build 要保存 tool/dependency versions、IP settings、constraints、timing 與 DRC 報告。不得靠關閉檢查、廣泛 false-path 或忽略 critical warning 假造 timing pass。

沒有板子、source、線材或授權時，完成所有仍可做的程式與模擬，明確標示 NOT_RUN/BLOCKED，留下最少的人工操作與可直接執行指令。不要只交付「理論上應該可以」。

既有人工核准的測試樣本不得自行重新核准／rebaseline。自行產生的資料稱 synthetic/reference data，不能冒稱 human-approved golden sample。

## 9. 工作範圍與交付要求

沿用現有 repo 結構，以少量必要模組完成，不先建立龐大的 plugin／framework。依依賴順序推進，保持 M1 主線可工作。

交付需包含：

- 可重現的 LiteX/HDL 產生、Vivado build／整合與部署指令。
- 板端 capture/sender、Host Python 套件與 examples、測試。
- bootstrap／doctor 或等價環境檢查方式、版本固定方式。
- 設計與 protocol 文件、驗收結果、剩餘問題。
- 完整的「從乾淨 checkout 到 PC 收到第一幀」操作流程。

不得覆寫使用者未提交修改、格式化 SD 卡、改動開機媒體、全域安裝套件或修改網路設定而不先確認。涉及 bitstream 載入／既有服務中斷，先說明影響並取得相應授權；避免同一已核准操作反覆詢問。

不要掃描與專案無關的私人資料，不將真實擷取畫面、密碼、私鑰或私有程式碼上傳外部服務。不要自動 commit／push 或發布 PR，除非我要求。

每個里程碑回報：完成了什麼、實際執行了什麼、結果證據、未驗證部分、下一個最小步驟。需要多次 session 時，確保 docs/progress.md 足以讓下一次從現況繼續。

## 10. 起始參考來源

以下是研究入口，不代表所有 main/master 版本已彼此相容。執行時查驗並記錄實際版本；不要因為這裡有網址就宣稱已讀過。

技能與 Codex：
- https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs
- https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling
- https://github.com/mattpocock/skills/tree/main/skills/engineering/domain-modeling
- https://github.com/mattpocock/skills/blob/main/docs/engineering/grill-with-docs.md
- https://github.com/mattpocock/skills/issues/1123
- https://developers.openai.com/codex/skills

PYNQ / LiteX：
- https://pynq.readthedocs.io/en/v3.1/pynq_overlays/pynqz2/pynqz2_base_overlay.html
- https://pynq.readthedocs.io/en/latest/pynq_libraries/video.html
- https://github.com/Xilinx/PYNQ
- https://github.com/litex-hub/litex-boards/blob/master/litex_boards/targets/tul_pynq_z2.py
- https://github.com/litex-hub/litex-boards/blob/master/litex_boards/platforms/tul_pynq_z2.py
- https://github.com/enjoy-digital/litex

LCD：
- https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A)
- https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(C)
- https://github.com/waveshareteam/LCD-show
- https://docs.radxa.com/en/rock3/rock3b/low-level-dev/spi-lcd

## 現在開始

先實際讀 repo、載入技能與進行非破壞性環境盤點，寫入初步研究結果。

第一次回覆只呈現：目前已確認的事實、推薦的最小可行資料路徑、最多 3 個當前阻塞決策。若沒有待決問題，給出共同理解摘要供我確認。不要只回覆「我會研究」，也不要在我確認前跳過 grill，直接大量產生 implementation。

記住主線：先讓 PC 的 Python 經 Ethernet 穩定取得來自 PYNQ-Z2 HDMI Input 的完整 RGB888 真實影格，再擴充其他功能。
