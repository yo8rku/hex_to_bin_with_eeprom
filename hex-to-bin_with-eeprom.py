
from pathlib import Path

INPUT_HEX = Path("protectx_HF_18f6722_BL_v2.4.X.production.hex")

OUTPUT_BIN = Path("protectx_HF_18f6722_BL_v2.4.X.production.bin")
OUTPUT_EEPROM = Path("protectx_HF_18f6722_BL_v2.4.X.production.eep.bin")

# Flash aplicație
FLASH_START = 0x1000
FLASH_END = 0xFFBF

# EEPROM în formatul Intel HEX pentru PIC18
EEPROM_BASE = 0xF00000

flash_memory = {}
eeprom_memory = {}
base = 0

for line in INPUT_HEX.read_text().splitlines():
    line = line.strip()

    if not line:
        continue

    if not line.startswith(":"):
        raise ValueError("Linie Intel HEX invalida")

    rec = bytes.fromhex(line[1:])
    count = rec[0]
    address = (rec[1] << 8) | rec[2]
    rectype = rec[3]
    data = rec[4:4 + count]

    if len(rec) != count + 5 or sum(rec) % 256 != 0:
        raise ValueError("Eroare de lungime/checksum HEX")

    if rectype == 0x00:
        absolute = base + address

        for i, b in enumerate(data):
            a = absolute + i

            # Flash aplicație
            if FLASH_START <= a <= FLASH_END:
                flash_memory[a] = b

            # EEPROM
            elif EEPROM_BASE <= a < EEPROM_BASE + 1024:
                eeprom_memory[a - EEPROM_BASE] = b

    elif rectype == 0x01:
        break

    elif rectype == 0x04:
        base = ((data[0] << 8) | data[1]) << 16

    elif rectype == 0x02:
        base = ((data[0] << 8) | data[1]) << 4


# --------------------------------------------------
# Genereaza BIN pentru Flash
# --------------------------------------------------

if not flash_memory:
    raise ValueError("Nu exista date in zona Flash a aplicatiei")

flash_last = max(flash_memory)

flash_image = bytearray([0xFF]) * (flash_last - FLASH_START + 1)

for address, value in flash_memory.items():
    flash_image[address - FLASH_START] = value

OUTPUT_BIN.write_bytes(flash_image)


# --------------------------------------------------
# Genereaza BIN pentru EEPROM
# --------------------------------------------------

if not eeprom_memory:
    raise ValueError("Nu exista date EEPROM in fisierul HEX")

eeprom_last = max(eeprom_memory)

eeprom_image = bytearray([0xFF]) * (eeprom_last + 1)

for address, value in eeprom_memory.items():
    eeprom_image[address] = value

OUTPUT_EEPROM.write_bytes(eeprom_image)


# --------------------------------------------------
# Rezultate
# --------------------------------------------------

print()
print("Conversie HEX finalizata!")
print()

print(f"FLASH BIN: {OUTPUT_BIN}")
print(f"Adresa PIC: 0x{FLASH_START:04X}")
print(f"Ultima adresa: 0x{flash_last:04X}")
print(f"Dimensiune: {len(flash_image)} bytes")

print()

print(f"EEPROM BIN: {OUTPUT_EEPROM}")
print("Adresa EEPROM: 0x0000")
print(f"Ultima adresa EEPROM: 0x{eeprom_last:04X}")
print(f"Dimensiune: {len(eeprom_image)} bytes")
