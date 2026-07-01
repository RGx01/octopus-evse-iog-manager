# Brand images

Home Assistant (2026.3+) loads these automatically for the
`octopus_evse_iog_manager` domain — they appear on the HACS card and device page.

- `icon.png` (256×256) / `icon@2x.png` (512×512) — square icon
- `logo.png` / `logo@2x.png` — brand image
- `kraken.svg` — editable source

Re-render after editing the SVG:

```bash
python3 -c "
import cairosvg
for name, size in [('icon.png',256),('icon@2x.png',512),('logo.png',256),('logo@2x.png',512)]:
    cairosvg.svg2png(url='kraken.svg', write_to=name, output_width=size, output_height=size)
"
```
