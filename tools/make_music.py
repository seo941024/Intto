"""Treblo에서 받은 배경음을 게임에 넣는다.

  art_inbox/music/title_v1.ogg     첫 화면, 시작 버튼 누르기 전
  art_inbox/music/lobby_v1.ogg     로비·대기실. 없으면 건너뛰고, 게임은 로비에서 조용히 둔다
  art_inbox/music/cloud_v1.ogg     1스테이지 구름섬
  art_inbox/music/mushroom_v1.ogg  2스테이지 버섯숲
  art_inbox/music/storm_v1.ogg     3스테이지 폭풍협곡
출력 public/assets/music/
  <이름>.ogg   받은 파일 그대로. 다시 압축하면 음질이 떨어지므로 손대지 않는다
  <이름>.mp3   OGG를 못 트는 사파리용 사본
  music.json   곡마다 음량 보정 배율 gain과, 끝 무음을 뺀 소리가 끝나는 시각 end. 단위 초
곡들이 같은 크기로 들리게 평균 음량을 TARGET_DB에 맞추되, 가장 큰 소리가 넘치지 않게 배율을 줄인다.
게임은 end 직전에서 다음 회차를 처음부터 겹쳐 틀어 곡을 끊김 없이 되풀이한다.
사용
  python tools/make_music.py
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "art_inbox" / "music"
OUT = ROOT / "public" / "assets" / "music"
TRACKS = ["title", "lobby", "cloud", "mushroom", "storm"]
TARGET_DB = -17.0  # 곡 전체 평균 음량 목표, dBFS
LEVEL_DB = {"lobby": -6.0}  # 곡마다 목표에서 더 줄이는 양. 로비는 이야기하며 기다리는 곳이라 경기 곡보다 작게 깐다
PEAK_MAX = 0.95  # 보정한 뒤 가장 큰 소리 상한
SILENT_DB = -50.0  # 이보다 작은 끝부분은 무음으로 보고 뺀다


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = {}
    for name in TRACKS:
        src = SRC / f"{name}_v1.ogg"
        if not src.exists():
            print(f"{name}: 원본 없음, 건너뜀")
            continue
        x, sr = sf.read(src, always_2d=True)
        loud = np.abs(x).max(1) > 10 ** (SILENT_DB / 20)
        end = (np.nonzero(loud)[0][-1] + 1) / sr
        rms = float(np.sqrt((x ** 2).mean()))
        gain = 10 ** ((TARGET_DB + LEVEL_DB.get(name, 0.0) - 20 * np.log10(rms)) / 20)
        gain = min(gain, PEAK_MAX / float(np.abs(x).max()))
        shutil.copyfile(src, OUT / f"{name}.ogg")
        sf.write(OUT / f"{name}.mp3", x, sr, format="MP3", bitrate_mode="VARIABLE", compression_level=0.4)
        spec[name] = {"gain": round(gain, 3), "end": round(end, 3)}
        mp3 = (OUT / f"{name}.mp3").stat().st_size / 1e6
        print(f"{name}: {len(x) / sr:.1f}초, 소리 끝 {end:.1f}초, 음량 배율 {gain:.2f}, mp3 {mp3:.1f}MB")
    (OUT / "music.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
