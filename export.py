"Export the talk from the notebook's exported cells: `slides.html` and `slides.pdf` next to it."
import asyncio, base64
from pathlib import Path
from fastcore.script import call_parse
from fastcdp.skill import CDP

from slides import render


async def html2pdf(html, pdf):
    "Print the page at `html` to `pdf` with a headless Chrome, honouring its `@page` size"
    cdp = await CDP.launch(headless=True)
    pg = await cdp.new_page()
    await pg.goto(Path(html).resolve().as_uri(), wait='idle')
    data = await pg.page.printToPDF(preferCSSPageSize=True, printBackground=True)
    Path(pdf).write_bytes(base64.b64decode(data))
    await cdp.quit()


@call_parse
def main(
    nb: str = 'code-complexity-naur.ipynb',  # The dialog holding the deck
):
    "Write `slides.html` and `slides.pdf` next to `nb`"
    d = Path(nb).parent
    (d / 'slides.html').write_text(render(nb))
    asyncio.run(html2pdf(d / 'slides.html', d / 'slides.pdf'))
    for f in ('slides.html', 'slides.pdf'): print(d / f, (d / f).stat().st_size // 1024, 'KB')
