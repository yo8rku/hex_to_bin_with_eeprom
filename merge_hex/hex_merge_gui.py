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
    """Copy bytes using the same address iteration as the original merge script."""
    if start < 0 or end < start:
        raise ValueError("Invalid range for {}: {:06X}-{:06X}".format(label, start, end))

    copied = 0
    for address in source.addresses():
        if start <= address <= end:
            target[address] = source[address]
            copied += 1
    return copied


def verify_range(source, target, start, end, label):
    """Verify using the original verify_hex.py algorithm (source._buf.items())."""
    count = 0
    for address, value in source._buf.items():
        if start <= address <= end:
            if target._buf.get(address) != value:
                raise ValueError(
                    "DIFERENTA: 0x{:08X} ({}) - source=0x{:02X}, target={}".format(
                        address, label, value,
                        "MISSING" if address not in target._buf
                        else "0x{:02X}".format(target._buf[address])
                    )
                )
            count += 1
    return count


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
        """Run the original merge sequence and verify the HEX written to disk."""
        def log(message):
            self.message_queue.put(("log", message))

        try:
            log("1 - Citire bootloader...")
            boot = IntelHex(str(path1))
            log("2 - Bootloader citit: {} bytes adresati".format(len(boot.addresses())))

            log("3 - Citire aplicatie...")
            app = IntelHex(str(path2))
            log("4 - Aplicatie citita: {} bytes adresati".format(len(app.addresses())))

            log("5 - Creare imagine HEX noua...")
            result = IntelHex()
            log("6 - Imagine noua creata")

            log("7 - Copiere bootloader (HEX 1)...")
            count_boot = copy_range(boot, result, start1, end1, "HEX 1")
            log("8 - Bootloader copiat: {} bytes".format(count_boot))

            log("9 - Copiere aplicatie (HEX 2)...")
            count_app = copy_range(app, result, start2, end2, "HEX 2")
            log("10 - Aplicatie copiata: {} bytes".format(count_app))

            log("11 - Copiere Device ID din HEX 2...")
            count_device = copy_range(
                app, result, DEVICE_ID_RANGE[0], DEVICE_ID_RANGE[1],
                DEVICE_ID_RANGE[2]
            )
            log("12 - Device ID copiat: {} bytes".format(count_device))

            log("13 - Copiere Configuration Words din HEX 1...")
            count_config = copy_range(
                boot, result, CONFIG_RANGE[0], CONFIG_RANGE[1],
                CONFIG_RANGE[2]
            )
            log("14 - Configuration Words copiate: {} bytes".format(count_config))

            log("15 - Copiere date speciale / EEPROM din HEX 2...")
            count_special = copy_range(
                app, result, SPECIAL_DATA_RANGE[0], SPECIAL_DATA_RANGE[1],
                SPECIAL_DATA_RANGE[2]
            )
            log("16 - Date speciale copiate: {} bytes".format(count_special))

            output_path = path1.resolve().parent / OUTPUT_NAME
            log("17 - Salvare HEX: {}".format(output_path))
            result.write_hex_file(str(output_path), byte_count=16)
            log("18 - HEX salvat")

            log("19 - Recitire HEX final de pe disc pentru verificare...")
            final = IntelHex(str(output_path))
            log("20 - HEX final recitit")

            log("21 - Verificare bootloader...")
            verified_boot = verify_range(
                boot, final, start1, end1, "Bootloader"
            )
            log("OK: {} bytes verificati".format(verified_boot))

            log("22 - Verificare aplicatie...")
            verified_app = verify_range(
                app, final, start2, end2, "Aplicatie"
            )
            log("OK: {} bytes verificati".format(verified_app))

            log("23 - Verificare Device ID...")
            verified_device = verify_range(
                app, final, DEVICE_ID_RANGE[0], DEVICE_ID_RANGE[1], "Device ID"
            )
            log("OK: {} bytes verificati".format(verified_device))

            log("24 - Verificare Configuration Words...")
            verified_config = verify_range(
                boot, final, CONFIG_RANGE[0], CONFIG_RANGE[1],
                "Configuration Words"
            )
            log("OK: {} bytes verificati".format(verified_config))

            log("25 - Verificare date speciale / EEPROM...")
            verified_special = verify_range(
                app, final, SPECIAL_DATA_RANGE[0], SPECIAL_DATA_RANGE[1],
                "Date speciale"
            )
            log("OK: {} bytes verificati".format(verified_special))

            raw = output_path.read_bytes()
            crc = zlib.crc32(raw) & 0xFFFFFFFF
            log("")
            log("==========================")
            log("VERIFICARE COMPLETA: SUCCES")
            log("Bootloader: {} bytes".format(verified_boot))
            log("Aplicatie: {} bytes".format(verified_app))
            log("Device ID: {} bytes".format(verified_device))
            log("Configuration Words: {} bytes".format(verified_config))
            log("Date speciale: {} bytes".format(verified_special))
            log("Output file size: {} bytes".format(len(raw)))
            log("CRC-32 IEEE (raw HEX file bytes): 0x{:08X}".format(crc))
            log("Disk path: {}".format(output_path))
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
                        "Merge and verification completed successfully.\n\n{}".format(
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
