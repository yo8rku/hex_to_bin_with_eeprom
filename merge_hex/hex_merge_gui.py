#!/usr/bin/env python3
"""
HEX Merger GUI for PIC firmware.

Requirements:
    python -m pip install intelhex

The GUI merges two Intel HEX files using independently editable address
ranges. It also preserves the auxiliary regions used by the original
merge_hex.py workflow:
  - Device ID: application file, 0x200000-0x200007
  - Configuration Words: bootloader file, 0x300000-0x30000D
  - Special data / EEPROM image: application file, 0xF00000-0xF0004F

The output is firmware_combined.hex in the common source folder.
"""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zlib

from intelhex import IntelHex


OUTPUT_NAME = "firmware_combined.hex"

DEVICE_ID_RANGE = (0x200000, 0x200007, "Device ID (from HEX 2)")
CONFIG_RANGE = (0x300000, 0x30000D, "Configuration Words (from HEX 1)")
SPECIAL_DATA_RANGE = (
    0xF00000,
    0xF0004F,
    "Special data / EEPROM image (from HEX 2)",
)


def parse_address(value):
    """Parse a hexadecimal address, with or without a 0x prefix."""
    value = value.strip().lower().replace("_", "")
    if value.startswith("0x"):
        value = value[2:]
    if not value:
        raise ValueError("Address field cannot be empty.")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise ValueError("Invalid hexadecimal address: {!r}".format(value)) from exc


def copy_range(source, target, start, end, label):
    """Copy bytes present in source within an inclusive address range."""
    if start < 0 or end < start:
        raise ValueError("Invalid range for {}: {:06X}-{:06X}".format(label, start, end))

    copied = 0
    for address in source.addresses():
        if start <= address <= end:
            value = source[address]
            if address in target and target[address] != value:
                raise ValueError(
                    "Address conflict at 0x{:06X} while copying {} "
                    "(existing 0x{:02X}, new 0x{:02X}).".format(
                        address, label, target[address], value
                    )
                )
            target[address] = value
            copied += 1
    return copied


def verify_range(source, merged, start, end, label):
    """Compare every source byte in an inclusive range with the merged HEX."""
    checked = 0
    for address in source.addresses():
        if start <= address <= end:
            if address not in merged:
                raise ValueError(
                    "Verification failed for {}: address 0x{:06X} is missing.".format(
                        label, address
                    )
                )
            if merged[address] != source[address]:
                raise ValueError(
                    "Verification failed for {} at 0x{:06X}: "
                    "source=0x{:02X}, merged=0x{:02X}.".format(
                        label, address, source[address], merged[address]
                    )
                )
            checked += 1
    return checked


class HexMergeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HEX Merger - PIC Firmware")
        self.root.geometry("800x660")
        self.root.minsize(700, 560)

        self.file1_var = tk.StringVar()
        self.file2_var = tk.StringVar()
        self.start1_var = tk.StringVar(value="000000")
        self.end1_var = tk.StringVar(value="0007FF")
        self.start2_var = tk.StringVar(value="000800")
        self.end2_var = tk.StringVar(value="00FFFF")

        self.message_queue = queue.Queue()
        self.merge_running = False
        self._build_ui()
        self.root.after(100, self._process_queue)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(7, weight=1)

        ttk.Label(
            main, text="HEX file 1 (Bootloader)", font=("", 10, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Entry(main, textvariable=self.file1_var).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=(0, 8)
        )
        ttk.Button(
            main, text="Browse...", command=lambda: self._browse(self.file1_var)
        ).grid(row=1, column=2)

        ttk.Label(
            main, text="HEX file 2 (Application)", font=("", 10, "bold")
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 4))
        ttk.Entry(main, textvariable=self.file2_var).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=(0, 8)
        )
        ttk.Button(
            main, text="Browse...", command=lambda: self._browse(self.file2_var)
        ).grid(row=3, column=2)

        ranges = ttk.LabelFrame(
            main, text="Address ranges (hexadecimal, inclusive)", padding=10
        )
        ranges.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        ranges.columnconfigure(1, weight=1)
        ranges.columnconfigure(3, weight=1)

        ttk.Label(ranges, text="Source").grid(row=0, column=0, sticky="w")
        ttk.Label(ranges, text="Start address").grid(row=0, column=1, sticky="w")
        ttk.Label(ranges, text="End address").grid(row=0, column=3, sticky="w")

        ttk.Label(ranges, text="HEX 1").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(ranges, textvariable=self.start1_var, width=14).grid(
            row=1, column=1, sticky="ew", padx=(0, 10)
        )
        ttk.Label(ranges, text="to").grid(row=1, column=2, padx=5)
        ttk.Entry(ranges, textvariable=self.end1_var, width=14).grid(
            row=1, column=3, sticky="ew"
        )

        ttk.Label(ranges, text="HEX 2").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(ranges, textvariable=self.start2_var, width=14).grid(
            row=2, column=1, sticky="ew", padx=(0, 10)
        )
        ttk.Label(ranges, text="to").grid(row=2, column=2, padx=5)
        ttk.Entry(ranges, textvariable=self.end2_var, width=14).grid(
            row=2, column=3, sticky="ew"
        )

        note = (
            "Additional fixed regions are copied automatically: Device ID "
            "from HEX 2, Configuration Words from HEX 1, and special data "
            "from HEX 2."
        )
        ttk.Label(main, text=note, wraplength=750).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        controls = ttk.Frame(main)
        controls.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.merge_button = ttk.Button(controls, text="Merge HEX", command=self.merge)
        self.merge_button.pack(side="left")
        ttk.Button(controls, text="Clear log", command=self.clear_log).pack(
            side="left", padx=8
        )

        log_frame = ttk.LabelFrame(main, text="Log / Result", padding=8)
        log_frame.grid(row=7, column=0, columnspan=3, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log = tk.Text(log_frame, height=14, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log.yview
        )
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._write_log("Ready. Select two Intel HEX files and press 'Merge HEX'.")

    def _browse(self, variable):
        filename = filedialog.askopenfilename(
            title="Select Intel HEX file",
            filetypes=[("Intel HEX files", "*.hex"), ("All files", "*.*")],
        )
        if filename:
            variable.set(filename)

    def _write_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", str(message).rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def merge(self):
        """Validate GUI inputs, then run all file processing in a worker thread."""
        if self.merge_running:
            return

        self.clear_log()
        try:
            path1 = Path(self.file1_var.get()).expanduser()
            path2 = Path(self.file2_var.get()).expanduser()

            if not path1.is_file() or not path2.is_file():
                raise ValueError("Please select two existing HEX files.")
            if path1.suffix.lower() != ".hex" or path2.suffix.lower() != ".hex":
                raise ValueError("Both input files must have the .hex extension.")
            if path1.resolve().parent != path2.resolve().parent:
                raise ValueError("Both source HEX files must be in the same folder.")

            start1 = parse_address(self.start1_var.get())
            end1 = parse_address(self.end1_var.get())
            start2 = parse_address(self.start2_var.get())
            end2 = parse_address(self.end2_var.get())
            if end1 < start1 or end2 < start2:
                raise ValueError(
                    "Each end address must be greater than or equal to its start address."
                )
        except Exception as exc:
            self._write_log("ERROR: {}".format(exc))
            messagebox.showerror("HEX Merger - Error", str(exc))
            return

        self.merge_running = True
        self.merge_button.configure(state="disabled")
        self._write_log("Starting merge in background...")
        self._write_log("HEX 1: {}".format(path1))
        self._write_log("HEX 2: {}".format(path2))
        self._write_log("HEX 1 range: 0x{:06X} - 0x{:06X}".format(start1, end1))
        self._write_log("HEX 2 range: 0x{:06X} - 0x{:06X}".format(start2, end2))

        worker = threading.Thread(
            target=self._merge_worker,
            args=(path1, path2, start1, end1, start2, end2),
            daemon=True,
        )
        worker.start()

    def _merge_worker(self, path1, path2, start1, end1, start2, end2):
        """Perform HEX I/O, merge, verification and CRC without touching Tk."""
        try:
            source1 = IntelHex(str(path1))
            source2 = IntelHex(str(path2))
            merged = IntelHex()

            count1 = copy_range(source1, merged, start1, end1, "HEX 1")
            count2 = copy_range(source2, merged, start2, end2, "HEX 2")
            self.message_queue.put(("log", "Copied HEX 1: {} bytes".format(count1)))
            self.message_queue.put(("log", "Copied HEX 2: {} bytes".format(count2)))

            fixed_regions = (
                (source2, DEVICE_ID_RANGE),
                (source1, CONFIG_RANGE),
                (source2, SPECIAL_DATA_RANGE),
            )
            for source, region in fixed_regions:
                start, end, label = region
                count = copy_range(source, merged, start, end, label)
                self.message_queue.put(
                    ("log", "Copied {}: {} bytes".format(label, count))
                )

            output_path = path1.resolve().parent / OUTPUT_NAME
            merged.write_hex_file(str(output_path), byte_count=16)

            self.message_queue.put(
                ("log", "Verifying generated HEX against source files...")
            )
            verified1 = verify_range(source1, merged, start1, end1, "HEX 1")
            verified2 = verify_range(source2, merged, start2, end2, "HEX 2")
            verified_device = verify_range(
                source2, merged, DEVICE_ID_RANGE[0], DEVICE_ID_RANGE[1],
                DEVICE_ID_RANGE[2]
            )
            verified_config = verify_range(
                source1, merged, CONFIG_RANGE[0], CONFIG_RANGE[1],
                CONFIG_RANGE[2]
            )
            verified_special = verify_range(
                source2, merged, SPECIAL_DATA_RANGE[0], SPECIAL_DATA_RANGE[1],
                SPECIAL_DATA_RANGE[2]
            )

            self.message_queue.put(
                ("log", "OK - HEX 1: {} bytes verified".format(verified1))
            )
            self.message_queue.put(
                ("log", "OK - HEX 2: {} bytes verified".format(verified2))
            )
            self.message_queue.put(
                ("log", "OK - Device ID: {} bytes verified".format(verified_device))
            )
            self.message_queue.put(
                ("log", "OK - Configuration Words: {} bytes verified".format(
                    verified_config
                ))
            )
            self.message_queue.put(
                ("log", "OK - Special data: {} bytes verified".format(
                    verified_special
                ))
            )

            raw = output_path.read_bytes()
            crc = zlib.crc32(raw) & 0xFFFFFFFF
            self.message_queue.put(("log", ""))
            self.message_queue.put(("log", "MERGE AND VERIFICATION SUCCESSFUL"))
            self.message_queue.put(
                ("log", "Output file size: {} bytes".format(len(raw)))
            )
            self.message_queue.put(
                ("log", "CRC-32 IEEE (raw HEX file bytes): 0x{:08X}".format(crc))
            )
            self.message_queue.put(("log", "Disk path: {}".format(output_path)))
            self.message_queue.put(("done", str(output_path)))
        except Exception as exc:
            self.message_queue.put(("error", str(exc)))

    def _process_queue(self):
        """Transfer worker messages to Tk widgets from the main GUI thread."""
        try:
            while True:
                kind, payload = self.message_queue.get_nowait()
                if kind == "log":
                    self._write_log(payload)
                elif kind == "done":
                    self.merge_running = False
                    self.merge_button.configure(state="normal")
                    messagebox.showinfo(
                        "HEX Merger",
                        "Merge and verification completed successfully.\\n\\n{}".format(
                            payload
                        ),
                    )
                elif kind == "error":
                    self.merge_running = False
                    self.merge_button.configure(state="normal")
                    self._write_log("")
                    self._write_log("ERROR: {}".format(payload))
                    messagebox.showerror("HEX Merger - Error", payload)
        except queue.Empty:
            pass

        self.root.after(100, self._process_queue)


def main():
    root = tk.Tk()
    HexMergeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
