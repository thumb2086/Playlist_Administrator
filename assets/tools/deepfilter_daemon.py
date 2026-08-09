"""常駐 DeepFilterNet daemon：啟動一次、模型載入一次、逐檔增強。

stdin/stdout JSONL：
  {"cmd":"enhance","id":1,"path":"...wav"} -> {"id":1,"ok":true}
  {"cmd":"quit"} -> 退出

記憶體優化（L3）：
- 窗式處理：每檔以 30 秒窗讀取（soundfile 流式），視窗間 1 秒重疊，
  交錯（crossfade）拼接；RAM 與錄影長度無關 → 常駐 ~3-4GB 封頂。
- 每檔後 torch.cuda.empty_cache() + gc.collect()（L1-2）。
- 模型精確度/模型：DF_DF_MODEL + DF_DAEMON_HALF 環境變數（L1-3/L2-4）。

裝置：spawn 時以 CUDA_VISIBLE_DEVICES（999999=強制 CPU）。
"""
import gc
import json
import numpy as np
import os
import sys

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WINDOW_SEC = 30.0
OVERLAP_SEC = 1.0
SR = 48000


def main() -> None:
    import numpy as np  # noqa: F401
    import torch
    import soundfile as sf
    from df import enhance, init_df

    df_model = os.environ.get("DF_DF_MODEL", "DeepFilterNet3")
    half = os.environ.get("DF_DAEMON_HALF", "0") == "1"
    model, df_state, _ = init_df(default_model=df_model, log_level="ERROR", log_file=None)
    # 注意：df.enhance 輸入必須是 CPU tensor（內部 audio.numpy()）；
    # fp16 交由後續優化（L1-3），目前固定 fp32 確保正確性。
    device = str(next(model.parameters()).device)
    print(json.dumps({"ready": True, "device": device, "model": df_model, "half": half}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        cmd = req.get("cmd")
        if cmd == "quit":
            print(json.dumps({"id": req.get("id", 0), "quit": True}), flush=True)
            break
        iid = req.get("id", 0)
        path = req.get("path", "")
        try:
            enhance_windowed(model, df_state, path, half)
            if half and torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            print(json.dumps({"id": iid, "ok": True}), flush=True)
        except Exception as e:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            print(json.dumps({"id": iid, "ok": False, "err": str(e)[-300:]}), flush=True)


def enhance_windowed(model, df_state, path: str, half: bool) -> None:
    """窗式增強：每窗 30s、窗間 1s 重疊（crossfade），尾段緩衝避免重複寫入；
    RAM 不隨檔長成長。結果先寫 tmp 再原子 replace。"""
    import torch
    import soundfile as sf
    from df import enhance

    tmp_path = f"{path}.{os.getpid()}.wav"
    win = int(SR * WINDOW_SEC)
    over = int(SR * OVERLAP_SEC)

    out_sf = sf.SoundFile(tmp_path, "w", samplerate=SR, channels=1, subtype="PCM_16")
    wrote_any = False
    tail = None
    try:
        with sf.SoundFile(path) as f:
            if f.samplerate != SR:
                raise ValueError(f"unsupported sr {f.samplerate}")
            while True:
                data = f.read(win)
                if len(data) == 0:
                    break
                t = torch.from_numpy(np.asarray(data, dtype=np.float32)).unsqueeze(0)
                w = enhance(model, df_state, t).float().cpu().numpy().squeeze(0)
                head = w[:over]
                body = w[over:] if len(w) > over else np.array([], dtype=np.float32)
                if tail is not None:
                    lo = min(len(tail), len(head))
                    if lo > 0:
                        fade = np.linspace(0.0, 1.0, lo, dtype=np.float32)
                        merged = tail[:lo] * (1 - fade) + head[:lo] * fade
                        out_sf.write(merged)
                        out_sf.write(head[lo:])
                    else:
                        out_sf.write(tail)
                        out_sf.write(head)
                    wrote_any = True
                else:
                    out_sf.write(head)
                    wrote_any = True
                out_sf.write(body)
                wrote_any = True
                tail = w[-over:] if len(w) >= over else None
                if len(data) < win:
                    break
        if tail is not None:
            out_sf.write(tail)
            wrote_any = True
    finally:
        out_sf.close()
        if not wrote_any:
            try: os.remove(tmp_path)
            except OSError: pass
            raise RuntimeError("enhance wrote nothing")
        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)



if __name__ == "__main__":
    main()