# Development

The slides are the exported note cells of `code-complexity-naur.ipynb`. A note containing only `---` starts a new slide. `::: {.cols}` puts its contents in two columns; `CRAFT.css` gives Solveit the same rule while editing.

Export everything:

```bash
python export.py
```

This writes `slides.html` (self-contained, local images inlined, arrow keys to move) and `slides.pdf` (one 16:9 page per slide, printed by a headless Chrome). `python slides.py code-complexity-naur.ipynb` renders the HTML alone and opens it in a browser; `python slides.py --help` lists its options.

The scripts need `mdhtml`, `aidialog`, `exhash`, `fastcdp` and `fastcore`, and Chrome for the PDF.
