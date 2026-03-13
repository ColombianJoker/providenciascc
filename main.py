#!/opt/local/bin/uv run
# /// script
# dependencies = [
#   "openpyxl",
#   "httpx",
#   "tqdm",
# ]
# ///

import sys
from pathlib import Path

import httpx
import openpyxl
from tqdm import tqdm


def main():
    xls_name = "Relatoria-CC-2026-02-12.xlsx"
    target_dir = Path("./ccdocs")
    target_dir.mkdir(exist_ok=True)

    try:
        # REMOVED read_only=True to allow hyperlink access
        xls = openpyxl.load_workbook(xls_name)
        print(f"'{xls_name}' cargado.", file=sys.stderr)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo {xls_name}", file=sys.stderr)
        return

    sheet = xls.active
    links = []

    # 1. Extract links (Starting from row 12, column index 7)
    # Note: iterating through the whole sheet without read_only is slower;
    # we use max_row if possible to limit the scope.
    for row in sheet.iter_rows(min_row=12):
        cell = row[7]
        if cell.hyperlink:
            links.append(cell.hyperlink.target)

    if not links:
        print("No se encontraron URLs con hipervínculos.", file=sys.stderr)
        return

    print(f"Iniciando descarga de {len(links)} documentos...", file=sys.stderr)

    # 2. Download with Progress Bar
    with httpx.Client(follow_redirects=True, timeout=15.0) as client:
        for link in tqdm(links, desc="Descargando", unit="doc"):
            try:
                # Extract filename from URL
                file_name = link.split("/")[-1]
                if not file_name.endswith((".asp", ".html", ".htm")):
                    file_name += ".html"

                file_path = target_dir / file_name

                response = client.get(link)
                response.raise_for_status()

                with open(file_path, "wb") as f:
                    f.write(response.content)

            except Exception as e:
                tqdm.write(f"Error en {link}: {e}", file=sys.stderr)

    print(f"\n¡Listo! Documentos guardados en {target_dir.absolute()}", file=sys.stderr)


if __name__ == "__main__":
    main()
