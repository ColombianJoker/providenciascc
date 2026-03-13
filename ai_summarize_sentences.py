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

    # 3. Authenticate with Google Gemini
    # Client looks for GEMINI_API_KEY in environment variables
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY not found in environment.", file=sys.stderr)
            return

        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Authentication Error: {e}", file=sys.stderr)
        return

    # 4. Processing Loop
    for file_str in tqdm(args.files, desc="Summarizing", unit="file"):
        file_path = Path(file_str)
        if not file_path.exists():
            continue

        try:
            # Determine MIME type based on extension
            ext = file_path.suffix.lower()
            mime_map = {
                ".pdf": "application/pdf",
                ".html": "text/html",
                ".txt": "text/plain",
            }
            mime_type = mime_map.get(ext, "text/plain")

            # Send to Gemini
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,  # Keep it deterministic for legal summaries
                ),
                contents=[
                    types.Part.from_bytes(
                        data=file_path.read_bytes(), mime_type=mime_type
                    ),
                    "Please provide the summary of this sentence as instructed in the system setup.",
                ],
            )

            # Save results
            output_file = file_path.with_suffix(".summary.txt")
            output_file.write_text(response.text, encoding="utf-8")

            # 5. Delay to manage rate limits
            if args.delay > 0:
                time.sleep(args.delay)

        except Exception as e:
            tqdm.write(f"Error processing {file_path.name}: {e}", file=sys.stderr)

    print(
        f"\nProcessing complete. Summaries saved in the source directory.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
