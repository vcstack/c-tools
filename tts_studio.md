# C-tool TTS Studio (VieNeu)

Cửa sổ Windows kiểu SubtitleEdit: mở JSON kịch bản, gen từng câu, sửa text, nghe thử. Logic VieNeu V4 trong `ctool/vieneu.py`.

## Cài rồi chạy

```bat
python -m pip install -r requirements-desktop.txt
python tts_studio.py
```

## EXE

```bat
build-tts-studio.cmd
```

Ra file: `dist\CtoolTTS\CtoolTTS.exe`

## JSON

Mở file trong `kich-ban\` (có `segments[].text`). Mỗi câu gen xong ghi ngay:

- audio: `<ten>.tts\<id>.mp3`
- trạng thái: `<ten>.json.tts.json`

Lỗi giữa chừng thì các câu trước vẫn giữ. Bấm **Gen chưa xong** để chạy tiếp.

## Skill kịch bản (Cursor + Claude Code)

Cùng một skill `kich-ban-truyen-ma`:

- Cursor: `.cursor/skills/kich-ban-truyen-ma/`
- Claude Code: `.claude/skills/kich-ban-truyen-ma/`

Mở repo C-Tools trong Claude Code rồi bảo gen truyện / `/kich-ban-truyen-ma`. Claude.ai web không đọc folder này — dán `SKILL.md` vào Project instructions nếu dùng web.

