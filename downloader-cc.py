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
        xls = openpyxl.load_workbook(xls_name)
        print(f"'{xls_name}' cargado.", file=sys.stderr)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo {xls_name}", file=sys.stderr)
        return

    sheet = xls.active
    links = []

    for row in sheet.iter_rows(min_row=12):
        cell = row[7]
        if cell.hyperlink:
            links.append(cell.hyperlink.target)

    if not links:
        print("No se encontraron URLs.", file=sys.stderr)
        return

    print(f"Verificando descargas previas...", file=sys.stderr)

    with httpx.Client(follow_redirects=True, timeout=15.0) as client:
        for link in tqdm(links, desc="Procesando", unit="doc"):
            try:
                # Compute filename
                file_name = link.split("/")[-1]
                if not file_name.endswith((".asp", ".html", ".htm")):
                    file_name += ".html"

                file_path = target_dir / file_name
                temp_path = file_path.with_suffix(".tmp")

                # Skip if already exists (The "Resume" logic)
                # Optional size check logic
                if file_path.exists():
                    if file_path.stat().st_size > 1024:  # Greater than 1KB
                        continue
                    else:
                        tqdm.write(
                            f"Refichando {file_name} (archivo muy pequeño/posible error)"
                        )

                # Download to a temporary file first
                # This prevents a partial download from being marked as 'complete' if the script crashes
                with client.stream("GET", link) as response:
                    response.raise_for_status()
                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)

                # Atomic rename: Once finished, change .tmp to .html
                temp_path.replace(file_path)

            except Exception as e:
                if "temp_path" in locals() and temp_path.exists():
                    temp_path.unlink()  # Clean up failed partial file
                tqdm.write(f"Error en {link}: {e}", file=sys.stderr)

    print(f"\n¡Listo! Documentos en {target_dir.absolute()}", file=sys.stderr)


if __name__ == "__main__":
    main()
