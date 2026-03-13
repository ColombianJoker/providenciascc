#!/usr/bin/env uv run
# /// script
# requires-python = "==3.11.*"
# dependencies = [
#   "google-genai",
#   "tqdm",
# ]
# ///

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from tqdm import tqdm

prg_name = "Summarizer"


def main():
    # Process Command Line Arguments
    parser = argparse.ArgumentParser(
        description="Process Colombian Constitutional Court sentences with Gemini."
    )
    parser.add_argument(
        "files", nargs="+", help="Local files to process (.html, .txt, .pdf)"
    )
    parser.add_argument(
        "--delay", "-d", type=float, default=1.0, help="Seconds to wait between files"
    )
    parser.add_argument(
        "--system", "-s", default="system.md", help="Path to system instruction file"
    )
    parser.add_argument(
        "--error-sleep",
        type=float,
        default=30.0,
        help="Seconds to wait after a non-fatal error",
    )
    parser.add_argument(
        "--force-summary",
        "-F",
        action="store_true",
        default=False,
        help="Force overwriting of files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Show messages",
    )
    parser.add_argument(
        "--DEBUG",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--suffix",
        "-S",
        action="store",
        type=str,
        default=".summary.md",
        help="Suffix to append to the summary",
    )
    parser.add_argument(
        "--model",
        action="store",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model to use",
    )
    parser.add_argument(
        "--md-dir",
        action="store",
        type=str,
        help="Directory to store the generated .md files",
    )
    parser.add_argument(
        "--pdf-dir",
        action="store",
        type=str,
        help="Directory to store the generated .pdf files",
    )
    parser.add_argument(
        "--min-size",
        action="store",
        type=int,
        default=1025,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--introduction",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    # 2. Load System Instructions
    system_path = Path(args.system)
    if not system_path.exists():
        print(
            f"Error: System instruction file '{args.system}' not found.",
            file=sys.stderr,
        )
        return
    system_instruction = system_path.read_text(encoding="utf-8")

    # Authenticate
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment.", file=sys.stderr)
        return
    client = genai.Client(api_key=api_key)

    # Preparar directorios de salida
    md_output_path = Path(args.md_dir) if args.md_dir else None
    if md_output_path:
        md_output_path.mkdir(parents=True, exist_ok=True)

    pdf_output_path = Path(args.pdf_dir) if args.pdf_dir else None
    if pdf_output_path:
        pdf_output_path.mkdir(parents=True, exist_ok=True)

    for file_str in tqdm(args.files, desc="Processing", unit="file"):
        file_path = Path(file_str)
        if not file_path.exists():
            continue

        # Definir ruta del archivo .md
        if md_output_path:
            output_md = md_output_path / (file_path.stem + args.suffix)
        else:
            output_md = file_path.with_suffix(args.suffix)

        # Lógica de salto (Resume)
        if output_md.exists() and (not args.force_summary):
            continue

        if file_path.stat().st_size < args.min_size:
            continue

        success = False
        retries = 0
        while not success and retries < 3:
            try:
                response = client.models.generate_content(
                    model=args.model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                    ),
                    contents=[
                        types.Part.from_bytes(
                            data=file_path.read_bytes(), mime_type="text/html"
                        ),
                        "Summarize this sentence as per system instructions.",
                    ],
                )

                # Filtrado de contenido
                header = f"# {file_path.stem}\n\n---\n\n"
                if not args.introduction:
                    lines = response.text.splitlines()
                    filtered_lines = []
                    found_start = False
                    for line in lines:
                        if found_start or line.strip().startswith("1."):
                            found_start = True
                            filtered_lines.append(line)
                    content = (
                        "\n".join(filtered_lines) if filtered_lines else response.text
                    )
                else:
                    content = response.text

                # Guardar Markdown
                output_md.write_text(header + content, encoding="utf-8")

                # --- Generación de PDF si se solicita ---
                if pdf_output_path:
                    output_pdf = pdf_output_path / (file_path.stem + ".pdf")
                    if not output_pdf.exists() or args.force_summary:
                        try:
                            subprocess.run(
                                [
                                    "pandoc",
                                    str(output_md),
                                    "-o",
                                    str(output_pdf),
                                    "--pdf-engine=weasyprint",
                                ],
                                check=True,
                                capture_output=True,
                            )
                            if args.verbose:
                                tqdm.write(f"PDF generado: {output_pdf.name}")
                        except Exception as pe:
                            tqdm.write(f"Error en PDF ({file_path.name}): {pe}")

                success = True
                if args.delay > 0:
                    time.sleep(args.delay)

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    tqdm.write("[QUOTA EXCEEDED] Deteniendo...")
                    sys.exit(1)
                retries += 1
                time.sleep(args.error_sleep)


if __name__ == "__main__":
    main()
