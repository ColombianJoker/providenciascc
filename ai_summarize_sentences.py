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
    parser.add_argument(
        "--error-sleep",
        type=float,
        default=30.0,
        help="Seconds to wait after a non-fatal error",
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

    # Authenticate with Google Gemini
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

    for file_str in tqdm(args.files, desc="Summarizing", unit="file"):
        file_path = Path(file_str)
        if not file_path.exists():
            continue

        # Resume logic: skip if already done
        output_file = file_path.with_suffix(".summary.txt")
        if output_file.exists():
            continue

        success = False
        retries = 0
        while not success and retries < 3:
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                    ),
                    contents=[
                        types.Part.from_bytes(
                            data=file_path.read_bytes(), mime_type="text/html"
                        ),
                        "Please provide the summary of this sentence as instructed in the system setup.",
                    ],
                )
                output_file.write_text(response.text, encoding="utf-8")
                success = True

                # Normal delay between successful requests
                if args.delay > 0:
                    time.sleep(args.delay)

            except Exception as e:
                err_str = str(e)

                # Hard Stop: Specific Quota Exhaustion
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    tqdm.write(
                        f"\n[QUOTA EXCEEDED] Stopping process to protect your account."
                    )
                    sys.exit(1)

                # Soft Retry: For temporary errors (500, 503, timeouts)
                retries += 1
                tqdm.write(
                    f"Error processing {file_path.name}: (Retry {retries}/3). Waiting {args.error_sleep}s..."
                )
                time.sleep(args.error_sleep)


if __name__ == "__main__":
    main()
