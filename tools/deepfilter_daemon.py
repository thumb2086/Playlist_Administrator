"""常駐 DeepFilterNet daemon：啟動一次、載入模型一次，逐檔增強。

stdin/stdout 走 JSONL：
  {"cmd":"enhance","id":1,"path":"C:\\...\\x.wav"} -> {"id":1,"ok":true}
  {"cmd":"quit"} -> 退出
增強結果直接覆寫原 wav（等同 CLI --no-suffix 行為）。

裝置控制：spawn 時設 CUDA_VISIBLE_DEVICES（999999=強制 CPU）。
"""
import json
import os
import sys

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    import numpy as np  # noqa: F401  (確保 numpy 先入場)
    import torch
    from df import enhance, init_df
    from df.io import load_audio, save_audio

    df_model = os.environ.get("DF_DF_MODEL", "DeepFilterNet3")
    half = os.environ.get("DF_DAEMON_HALF", "0") == "1"
    model, df_state, _ = init_df(
        default_model=df_model, log_level="ERROR", log_file=None
    )
    if half and torch.cuda.is_available():
        model = model.half()
        df_state.config = df_state.config  # 保持設定object；內部 hop/fft 不受精度影響
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
        tmp_path = f"{path}.{os.getpid()}.wav"
        try:
            audio, meta = load_audio(path)
            sr = meta.sample_rate
            t = torch.as_tensor(audio)
            if t.ndim == 1:
                t = t.unsqueeze(0)
            if half and torch.cuda.is_available():
                t = t.half().cuda()
                model_half = True
            else:
                t = t.float()
                model_half = False
            out = enhance(model, df_state, t) if not half else enhance(model, df_state, t)
            out = out.float()
            save_audio(tmp_path, out.squeeze(0).cpu(), sr)
            if os.path.exists(path):
                os.replace(tmp_path, path)  # 原子替換，避免 crash 留半截 wav
            else:
                os.rename(tmp_path, path)
            print(json.dumps({"id": iid, "ok": True}), flush=True)
        except Exception as e:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except OSError: pass
            print(json.dumps({"id": iid, "ok": False, "err": str(e)[-300:]}), flush=True)


if __name__ == "__main__":
    main()