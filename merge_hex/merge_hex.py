
from intelhex import IntelHex

print("1 - Start", flush=True)

boot = IntelHex("bootloader.hex")
print("2 - Bootloader citit", flush=True)

app = IntelHex("application.hex")
print("3 - Aplicatie citita", flush=True)

result = IntelHex()
print("4 - Imagine noua creata", flush=True)

print("5 - Copiere bootloader", flush=True)
for addr in boot.addresses():
    if 0 <= addr <= 0x07FF:
        result[addr] = boot[addr]

print("6 - Bootloader copiat", flush=True)

print("7 - Copiere aplicatie", flush=True)

for addr in app.addresses():
    if 0x0800 <= addr <= 0xFFFF:
        result[addr] = app[addr]

print("8 - Aplicatie copiata", flush=True)

print("9 - Copiere Device ID", flush=True)
for addr in app.addresses():
    if 0x200000 <= addr <= 0x200007:
        result[addr] = app[addr]

print("10 - Device ID copiat", flush=True)

print("11 - Copiere configuratie", flush=True)
for addr in boot.addresses():
    if 0x300000 <= addr <= 0x30000D:
        result[addr] = boot[addr]

print("12 - Configuratie copiata", flush=True)

print("13 - Copiere date speciale", flush=True)
for addr in app.addresses():
    if 0xF00000 <= addr <= 0xF0004F:
        result[addr] = app[addr]

print("14 - Date speciale copiate", flush=True)

print("15 - Salvare HEX", flush=True)
result.write_hex_file("firmware_combined.hex")

print("16 - FINALIZAT", flush=True)
