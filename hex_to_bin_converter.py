#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HEX to BIN Converter
Converts a Microchip/PIC Intel HEX file into:
  <source_name>.bin       - application Flash image
  <source_name>.eep.bin   - EEPROM image

No third-party Python packages are required.
"""

from pathlib import Path
import zlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# Settings copied from the working conversion script
FLASH_START = 0x1000
FLASH_END = 0xFFBF
EEPROM_BASE = 0xF00000
EEPROM_SIZE = 1024


def convert_hex_file(input_path: Path, flash_start: int, flash_end: int):
    """Parse Intel HEX and create the Flash and EEPROM binary images."""
    if not (0 <= flash_start <= 0xFFFFFF and 0 <= flash_end <= 0xFFFFFF):
        raise ValueError("Adresele Flash trebuie sa fie intre 0x000000 si 0xFFFFFF.")
    if flash_start > flash_end:
        raise ValueError("Adresa de start Flash trebuie sa fie mai mica sau egala cu adresa finala.")
    flash_memory = {}
    eeprom_memory = {}
    base = 0
    eof_found = False

    try:
        lines = input_path.read_text(encoding="ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("Fisierul HEX nu este in format ASCII.") from exc

    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        if not line.startswith(":"):
            raise ValueError(f"Linia {line_number}: inregistrare Intel HEX invalida.")

        try:
            record = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise ValueError(f"Linia {line_number}: continut HEX invalid.") from exc

        if len(record) < 5:
            raise ValueError(f"Linia {line_number}: inregistrare prea scurta.")

        count = record[0]
        address = (record[1] << 8) | record[2]
        record_type = record[3]
        data = record[4:4 + count]

        if len(record) != count + 5 or (sum(record) & 0xFF) != 0:
            raise ValueError(f"Linia {line_number}: lungime sau checksum incorect.")

        if record_type == 0x00:  # Data record
            absolute_address = base + address

            for offset, value in enumerate(data):
                current_address = absolute_address + offset

                if flash_start <= current_address <= flash_end:
                    flash_memory[current_address] = value
                elif EEPROM_BASE <= current_address < EEPROM_BASE + EEPROM_SIZE:
                    eeprom_memory[current_address - EEPROM_BASE] = value

        elif record_type == 0x01:  # EOF
            eof_found = True
            break

        elif record_type == 0x04:  # Extended linear address
            if count != 2:
                raise ValueError(f"Linia {line_number}: record 04 invalid.")
            base = ((data[0] << 8) | data[1]) << 16

        elif record_type == 0x02:  # Extended segment address
            if count != 2:
                raise ValueError(f"Linia {line_number}: record 02 invalid.")
            base = ((data[0] << 8) | data[1]) << 4

        # Other Intel HEX record types are ignored, as in the original script.

    if not eof_found:
        raise ValueError("Fisierul HEX nu contine inregistrarea EOF (01).")

    if not flash_memory:
        raise ValueError(
            f"Nu exista date in zona Flash a aplicatiei "
            f"(0x{flash_start:X}-0x{flash_end:X})."
        )

    if not eeprom_memory:
        raise ValueError("Nu exista date EEPROM in fisierul HEX.")

    flash_last = max(flash_memory)
    flash_image = bytearray([0xFF]) * (flash_last - flash_start + 1)
    for address, value in flash_memory.items():
        flash_image[address - flash_start] = value

    eeprom_last = max(eeprom_memory)
    eeprom_image = bytearray([0xFF]) * (eeprom_last + 1)
    for address, value in eeprom_memory.items():
        eeprom_image[address] = value

    # Keep both outputs beside the selected HEX file and use its base name.
    output_bin = input_path.with_suffix(".bin")
    output_eep = input_path.with_name(input_path.stem + ".eep.bin")

    # Files are written only after the complete HEX file has been validated.
    output_bin.write_bytes(flash_image)
    output_eep.write_bytes(eeprom_image)

    flash_crc32 = zlib.crc32(flash_image) & 0xFFFFFFFF
    eeprom_crc32 = zlib.crc32(eeprom_image) & 0xFFFFFFFF

    return {
        "flash_path": output_bin,
        "eeprom_path": output_eep,
        "flash_last": flash_last,
        "eeprom_last": eeprom_last,
        "flash_size": len(flash_image),
        "eeprom_size": len(eeprom_image),
        "flash_crc32": flash_crc32,
        "eeprom_crc32": eeprom_crc32,
    }


class HexToBinApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HEX to BIN Converter")
        self.root.geometry("740x650")
        self.root.minsize(650, 420)

        self.selected_file = tk.StringVar()
        self.flash_start_var = tk.StringVar(value=f"{FLASH_START:X}")
        self.flash_end_var = tk.StringVar(value=f"{FLASH_END:X}")
        self.status_text = tk.StringVar(value="Selecteaza un fisier Intel HEX pentru conversie.")

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="HEX to BIN Converter",
            font=("Segoe UI", 16, "bold")
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            main,
            text="Conversie firmware PIC: Flash BIN + EEPROM BIN",
            font=("Segoe UI", 10)
        )
        subtitle.pack(anchor="w", pady=(2, 18))

        file_frame = ttk.LabelFrame(main, text="Fisier sursa (.hex)", padding=12)
        file_frame.pack(fill="x")

        entry = ttk.Entry(file_frame, textvariable=self.selected_file)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_button = ttk.Button(file_frame, text="Browse...", command=self.browse_file)
        browse_button.pack(side="right")

        settings = ttk.LabelFrame(main, text="Configuratie conversie", padding=12)
        settings.pack(fill="x", pady=14)

        flash_row = ttk.Frame(settings)
        flash_row.pack(fill="x", anchor="w")
        ttk.Label(flash_row, text="Flash start (hex):").pack(side="left")
        ttk.Entry(flash_row, textvariable=self.flash_start_var, width=12).pack(side="left", padx=(6, 18))
        ttk.Label(flash_row, text="Flash end (hex):").pack(side="left")
        ttk.Entry(flash_row, textvariable=self.flash_end_var, width=12).pack(side="left", padx=6)
        ttk.Label(
            settings,
            text=f"EEPROM: 0x{EEPROM_BASE:06X} - 0x{EEPROM_BASE + EEPROM_SIZE - 1:06X} (1024 bytes)"
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(settings, text="Introdu adresele Flash in hexazecimal, cu sau fara prefixul 0x.").pack(anchor="w")

        self.convert_button = ttk.Button(
            main,
            text="Convert to bin",
            command=self.convert,
        )
        self.convert_button.pack(fill="x", ipady=5)

        status_frame = ttk.LabelFrame(main, text="Rezultat", padding=10)
        status_frame.pack(fill="both", expand=True, pady=(14, 0))

        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_text,
            justify="left",
            anchor="nw",
            wraplength=640
        )
        self.status_label.pack(fill="both", expand=True)

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Selecteaza fisierul HEX",
            filetypes=[
                ("Intel HEX files", "*.hex"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.selected_file.set(filename)
            self.status_text.set("Fisier selectat. Apasa «Convert to bin» pentru conversie.")

    def convert(self):
        filename = self.selected_file.get().strip()
        if not filename:
            messagebox.showwarning("Fisier lipsa", "Selecteaza mai intai un fisier .hex.")
            return

        input_path = Path(filename)
        if not input_path.is_file():
            messagebox.showerror("Fisier invalid", "Fisierul selectat nu exista.")
            return
        if input_path.suffix.lower() != ".hex":
            messagebox.showerror("Format invalid", "Te rog selecteaza un fisier cu extensia .hex.")
            return

        self.convert_button.configure(state="disabled")
        self.status_text.set("Conversie in curs...")
        self.root.update_idletasks()

        try:
            start_text = self.flash_start_var.get().strip().lower().removeprefix("0x")
            end_text = self.flash_end_var.get().strip().lower().removeprefix("0x")
            flash_start = int(start_text, 16)
            flash_end = int(end_text, 16)
            result = convert_hex_file(input_path, flash_start, flash_end)
        except Exception as exc:
            self.status_text.set("Conversia a esuat.")
            messagebox.showerror("Eroare la conversie", str(exc))
            return
        finally:
            self.convert_button.configure(state="normal")

        report = (
            "Conversie HEX finalizata cu succes!\n\n"
            f"FLASH BIN: {result['flash_path'].name}\n"
            f"  Adresa de start: 0x{flash_start:X}\n"
            f"  Ultima adresa:   0x{result['flash_last']:X}\n"
            f"  Dimensiune:      {result['flash_size']} bytes\n"
            f"  CRC-32:          0x{result['flash_crc32']:08X}\n\n"
            f"EEPROM BIN: {result['eeprom_path'].name}\n"
            "  Adresa EEPROM:   0x0000\n"
            f"  Ultima adresa:   0x{result['eeprom_last']:04X}\n"
            f"  Dimensiune:      {result['eeprom_size']} bytes\n"
            f"  CRC-32:          0x{result['eeprom_crc32']:08X}\n\n"
            f"Folder: {input_path.parent}"
        )
        # Afiseaza raportul direct in zona „Rezultat”, fara popup de confirmare.
        self.status_text.set(report)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    HexToBinApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
