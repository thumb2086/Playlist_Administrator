# 音軌抽取×DeepFilterNet 記憶體優化方案

狀態：v2.7.13（daemon 根治版）已可完整跑完；本篇針對「運作時系統 RAM 8–10GB 偏高、門檻高」的**下一步優化**。

## 現況診斷（為什麼吃 8–10GB）

| 佔用來源 | 估計 |
|---|---|
| python + torch + numpy 常駐（daemon 基座） | ~1.5–2 GB |
| DeepFilterNet3 模型 fp32（GPU 用 + host 鏡像） | ~1.7–2.5 GB |
| 10 分鐘段的 STFT 特徵 buffer（bins×frames×fp32） | ~0.9–1.2 GB |
| ffmpeg 抽出/編碼（2 線）各解碼長影片 | ~0.4–1.0 GB |
| 併發時重疊（ffmpeg 2 × daemon 同時峰值） | 疊加 |

縮小段長實測無感：因為**基底（torch+模型）才是大頭**，特徵 buffer 已是次要。

## 優化方案（依收益/成本排序）

### L1 — 快、低風險（←工程量 1–2 小時）
1. **ffmpeg 每檔限制單線程解碼 `-threads 1`**：兩顆 worker 的 RSS 各降一半（decode 用核心數自動拉高，但我們同時只 2 worker）。
2. **daemon 內 `torch.cuda.empty_cache()` + 定期 `gc.collect()`（每檔後）**：把 caching allocator 佔住不還的碎片還給系統，長期 batch 時能收 1–2GB。
3. **daemon 用 half（fp16）推斷**：`model.half(); df_state 遷 fp16`——host 鏡像佔用直接減半（~1GB 起）；品質對語音無感（聽感測不出）。DeepFilterNet 內部 `as_complex` 等是 float64?（實測後再定）。

### L2 — 中（2–4 小時）
4. **改用 DeepFilterNet2 或 mask_only 模式**（`init_df(mask_only=True, default_model='DeepFilterNet2')`）：
   - 模型小了 3–4 倍（~0.4–0.6GB），運算更快；語音降噪品質仍可接受（實測對照 <700ms 長度段）。
   - 可做成設定「品質/速度」二選一，預設 DF3。
5. **影片抽出降並行到 1 個（與 daemon 不同時重疊）**：將 Phase 1/3 的 ffmpeg pool 設 `pool=1`（抽出與編碼本就把 RAM 高峰隔開），保留 2 僅在「不播放」時可選（設定項目）。

## L3 — 根治級（半天–1 天）
6. **daemon 內部窗式處理（真正的 root fix）**：
   - 不再 `load_audio()` 整個段；用 `torchaudio`/`soundfile` 逐窗讀（如 30–60s/窗），`df.enhance` 每窗處理後**重疊拼接**（窗間 1–2s 重疊、去邊界演算法延遲 n_fft-hop）。
   - 效果：**記憶體與段長無關**，常駐 3–4GB 封頂，任何長度都不再增加。
   - 完全符合 df 的 API（`enhance` 一次吃一窗）。
7. **模型權重移入 shared 或用 mmap**：PyTorch 無原生零拷貝；可改用 `torch.load(map_location='meta')`+lazy 只留 GPU…（對 Windows + torch 2.6 收益存疑，預設不做）。

## 預期曲線

| 方案集合 | 預估 RAM | 風險 |
|---|---|---|
| 現狀 2.7.13 | 8–10GB | 穩定 |
| L1(1+2+3) | ~5–7GB | 低 |
| L1+L2(4+5) | ~4–5GB | 中（品質對照） |
| L1–L3（全） | **~3–4GB 封頂** | 中（需 e2e） |

## 建議執行順序
1. 先上 L1-1/2/3（一次 commit，1–2 小時驗證）
2. 若仍 >5GB → 上 L2-4（DF2 選項，品質 A/B）
3. 最終目標：L3-6 窗式（封頂）— 由 daemon 協定不變，只管內部讀取

所有點都已附原則引導，實作前先各跑一份 `torch.cuda.memory_summary()` / `psutil` 對照數據。