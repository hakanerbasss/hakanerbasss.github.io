"""SRT altyazı dosyası üretimi."""


def _fmt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(chunks: list[str], durations: list[float]) -> str:
    lines: list[str] = []
    t = 0.0
    for i, (text, dur) in enumerate(zip(chunks, durations), 1):
        start, end = _fmt(t), _fmt(t + dur)
        words = text.split()
        if len(words) > 10:
            mid = len(words) // 2
            text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        t += dur
    return "\n".join(lines)
