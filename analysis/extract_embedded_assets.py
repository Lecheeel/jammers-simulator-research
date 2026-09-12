from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description="Extract embedded Wails/WebView2 assets from the sample.")
parser.add_argument("--sample", type=Path, default=Path(__file__).parents[1] / "sample" / "jammers-simulator.exe")
parser.add_argument("--out", type=Path, default=Path(__file__).parent / "embedded")
args = parser.parse_args()

exe = args.sample.resolve()
data = exe.read_bytes()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)

assets = {
    "index.html": (8585835, 8599407),
    "wails-runtime.js": (8582274, 8585802),
    "index-BYdydaNq.js": (8827142, 9093416),
    "service-CMl-d-hg.js": (8751821, 8826167),
}
for name, (start, end) in assets.items():
    chunk = data[start:end]
    (out / name).write_bytes(chunk)
    print(name, start, end, len(chunk))

# Keep a UTF-8-oriented string index for static inspection.
text = data.decode("utf-8", errors="ignore")
terms = [
    "GeneratePractice", "DefaultGenerationRules", "bearingnoise", "counterSource",
    "insideJammerDisk", "directionalCoverage", "normalizeDegrees", "radius",
    "noise-seed", "scenario", "jammer", "practice", "formal",
]
with (out / "string-context.txt").open("w", encoding="utf-8") as f:
    for term in terms:
        f.write(f"\n### {term}\n")
        pos = 0
        for _ in range(20):
            pos = text.find(term, pos)
            if pos < 0:
                break
            f.write(f"{pos}: {text[max(0, pos-160):pos+420]}\n")
            pos += len(term)
