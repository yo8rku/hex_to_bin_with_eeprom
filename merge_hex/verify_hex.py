
from intelhex import IntelHex

boot = IntelHex("bootloader.hex")
app = IntelHex("application.hex")
final = IntelHex("firmware_combined.hex")

def compare(source, target, start, end):
    count = 0

    for addr, value in source._buf.items():
        if start <= addr <= end:
            if target._buf.get(addr) != value:
                print(f"DIFERENTA: 0x{addr:08X}")
                return False

            count += 1

    print(f"OK: {count} bytes verificati")
    return True

print("\nVERIFICARE HEX FINAL\n", flush=True)

print("1. Bootloader:", flush=True)
ok1 = compare(boot, final, 0x000000, 0x0007FF)

print("\n2. Aplicatie:", flush=True)
ok2 = compare(app, final, 0x000800, 0x00FFFF)

print("\n3. Device ID:", flush=True)
ok3 = compare(app, final, 0x200000, 0x200007)

print("\n4. Configuration Words:", flush=True)
ok4 = compare(boot, final, 0x300000, 0x30000D)

print("\n5. Date speciale:", flush=True)
ok5 = compare(app, final, 0xF00000, 0xF0004F)

print("\n==========================", flush=True)

if all([ok1, ok2, ok3, ok4, ok5]):
    print("VERIFICARE COMPLETA: SUCCES")
else:
    print("VERIFICARE ESUATA!")
