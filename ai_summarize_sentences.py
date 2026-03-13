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
        help="Force overwriting of .summary.txt files",
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
        help="Suffix to append (from base file) to the summary",
    )
    parser.add_argument(
        "--model",
        action="store",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model to use",
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
    if args.verbose or args.DEBUG:
        print(f"{prg_name}: '{args.system}' cargado.", file=sys.stderr)

    # Authenticate with Google Gemini
    # Client looks for GEMINI_API_KEY in environment variables
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY not found in environment.", file=sys.stderr)
            return

        client = genai.Client(api_key=api_key)
        if args.verbose or args.DEBUG:
            print(f"{prg_name}: got and read the API key.", file=sys.stderr)
    except Exception as e:
        print(f"Authentication Error: {e}", file=sys.stderr)
        return

    if args.DEBUG:
        print(f"{prg_name}: using {args.model} model", file=sys.stderr)
        print(
            f"{prg_name}: using '{args.suffix}' to append to summary name",
            file=sys.stderr,
        )
    if args.force_summary:
        print(f"{prg_name}: overwriting summaries.", file=sys.stderr)

    for file_str in tqdm(args.files, desc="Summarizing", unit="file"):
        if args.DEBUG:
            print(f"{prg_name}: '{file_str=}'", file=sys.stderr)
        file_path = Path(file_str)
        if not file_path.exists():
            continue
        if args.verbose:
            tqdm.write(
                f"{prg_name}:  '{file_path}'  ....",
            )
        # Resume logic: skip if already done
        output_file = file_path.with_suffix(args.suffix)
        if output_file.exists() and (not args.force_summary):
            if args.verbose:
                tqdm.write(
                    f"{prg_name}: '{output_file}' exists and overwriting...",
                )
            continue
        file_size = file_path.stat().st_size
        if file_size < args.min_size:
            if args.verbose or args.DEBUG:
                tqdm.write(
                    f"{prg_name}: skipping '{file_path.name}' ({file_size} bytes) - below min size {args.min_size}."
                )
            continue
        success = False
        retries = 0
        while not success and retries < 3:
            try:
                if args.DEBUG:
                    tqdm.write(
                        f"DEBUG: sending '{file_path.name}' to Gemini...",
                    )

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

                header = f"# {file_path.stem}\n\n---\n\n"
                if not args.introduction:
                    # --- Lógica de filtrado ---
                    full_text = response.text
                    lines = full_text.splitlines()
                    filtered_lines = []
                    found_start = False

                    for line in lines:
                        # Si ya encontramos el inicio o la línea actual empieza con "1."
                        if found_start or line.strip().startswith("1."):
                            found_start = True
                            filtered_lines.append(line)

                    # Unir las líneas filtradas o usar el texto original si no se encontró el patrón
                    filtered_text = (
                        "\n".join(filtered_lines) if filtered_lines else full_text
                    )

                    # Guardar con encabezado y línea en blanco
                    output_file.write_text(header + filtered_text, encoding="utf-8")
                else:
                    # Guardar texto completo con encabezado y línea en blanco
                    output_file.write_text(header + response.text, encoding="utf-8")
                success = True

                if args.delay > 0:
                    time.sleep(args.delay)

            except Exception as e:
                err_str = str(e)

                # 1. Provide detailed output if DEBUG is on
                if args.DEBUG:
                    tqdm.write(f"\n--- DEBUG API ERROR FOR {file_path.name} ---")
                    tqdm.write(err_str)
                    tqdm.write("-------------------------------------------\n")

                # 2. Hard Stop for Quota Issues
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    tqdm.write(
                        f"\n[QUOTA EXCEEDED] Proceso detenido. Verifique su cuenta de facturación."
                    )
                    sys.exit(1)

                # 3. Standard error handling
                retries += 1
                tqdm.write(
                    f"Error processing '{file_path.name}': (Retry {retries}/3). Sleeping {args.error_sleep}s..."
                )
                time.sleep(args.error_sleep)


if __name__ == "__main__":
    main()
