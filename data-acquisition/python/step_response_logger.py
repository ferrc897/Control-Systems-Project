import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
import serial


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for serial capture."""
    parser = argparse.ArgumentParser(
        description="Trigger STM32 step response over UART and log telemetry to CSV."
    )
    parser.add_argument(
        "--port",
        required=True,
        help="Serial port name (e.g., /dev/ttyUSB0, /dev/ttyACM0, or COM3).",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="UART baud rate (default: 115200).",
    )
    parser.add_argument(
        "--trigger",
        default="S\n",
        help="Trigger payload sent to STM32 to start the step response (default: 'S\\n').",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Capture duration in seconds after starting (default: 5.0). Use 0 for manual stop (Ctrl+C).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Serial read timeout in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV file path (default: step_response_YYYYMMDD_HHMMSS.csv).",
    )
    return parser.parse_args()


def build_output_path(custom_path: Path | None) -> Path:
    """Resolve output CSV path and ensure parent directory exists."""
    if custom_path is not None:
        output_path = custom_path
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"step_response_{timestamp}.csv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def parse_telemetry_line(line: str) -> list[float] | None:
    """Parse a comma-separated line 'tiempo,input,rpms,corriente' into floats."""
    cleaned = line.strip()
    if not cleaned:
        return None

    # Ignore optional debug/status messages from firmware
    if cleaned.startswith("#") or cleaned.startswith("INFO"):
        return None

    parts = [token.strip() for token in cleaned.split(",")]
    if len(parts) != 4:
        return None

    try:
        tiempo = float(parts[0])
        step_input = float(parts[1])
        rpms = float(parts[2])
        corriente = float(parts[3])
    except ValueError:
        return None

    return [tiempo, step_input, rpms, corriente]


def run_capture(args: argparse.Namespace) -> None:
    """Send start trigger over UART and record CSV telemetry."""
    output_path = build_output_path(args.output)
    fieldnames = ["tiempo", "input", "rpms", "corriente"]
    samples_written = 0

    print(f"Opening serial port {args.port} at {args.baudrate} baud...")
    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baudrate,
            timeout=args.timeout,
        ) as ser:
            # Allow USB-UART / MCU state to settle and flush stale buffer bytes
            time.sleep(0.2)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            trigger_bytes = args.trigger.encode("utf-8")
            print(f"Sending trigger command ({trigger_bytes!r}) to STM32...")
            ser.write(trigger_bytes)
            ser.flush()

            start_time = time.monotonic()
            print(f"Logging data to '{output_path}'. Press Ctrl+C to stop.")

            with output_path.open(mode="w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(fieldnames)

                while True:
                    if args.duration > 0 and (time.monotonic() - start_time) >= args.duration:
                        print("Capture duration reached.")
                        break

                    raw_line = ser.readline()
                    if not raw_line:
                        continue

                    decoded_line = raw_line.decode("utf-8", errors="replace")
                    row = parse_telemetry_line(decoded_line)
                    if row is not None:
                        writer.writerow(row)
                        samples_written += 1

    except serial.SerialException as exc:
        print(f"Serial error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCapture interrupted by user (Ctrl+C).")

    print(f"Done. Wrote {samples_written} samples to '{output_path}'.")


def main() -> None:
    """Entry point."""
    args = parse_args()
    run_capture(args)


if __name__ == "__main__":
    main()