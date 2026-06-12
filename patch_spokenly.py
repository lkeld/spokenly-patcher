#!/usr/bin/env python3
# patch_spokenly.py — unlock the recording-display picker (panel <-> notch)
# Redirects the paywall branch in sub_100125DC0 straight into the apply branch.
# Run:  sudo python3 patch_spokenly.py

import struct, subprocess, sys, os, shutil

APP    = "/Applications/Spokenly.app"
BIN    = os.path.join(APP, "Contents/MacOS/Spokenly")
HERE   = os.path.dirname(os.path.abspath(__file__))
ORIG   = os.path.join(HERE, "Spokenly.orig")

# MOV W0,#3 ; MOV X20,X19 ; BL sub_100022FC0   (the paywall block @ 0x100125FB0)
PATTERN = bytes.fromhex("60008052" "F40313AA" "02F4FB97")
# B loc_100125F60   (jump back into the apply path)
PATCH   = bytes.fromhex("ECFFFF17")
PATCH_OFFSET_IN_PATTERN = 0

FAT_MAGIC = 0xCAFEBABE
CPU_ARM64 = 0x0100000C

def arm64_ranges(data):
    if struct.unpack(">I", data[:4])[0] == FAT_MAGIC:          # universal binary
        n = struct.unpack(">I", data[4:8])[0]
        for i in range(n):
            cpu, _, off, size, _ = struct.unpack(">5I", data[8+20*i:28+20*i])
            if cpu == CPU_ARM64:
                yield off, size
    else:                                                       # thin
        yield 0, len(data)

def sh(*cmd):
    print("    $", " ".join(cmd))
    subprocess.run(cmd, check=True)

def clean_bundle():
    macos = os.path.join(APP, "Contents/MacOS")
    for f in os.listdir(macos):
        if f != "Spokenly":                      # keep only the real executable
            print(f"[*] removing stray bundle file: {f}")
            os.remove(os.path.join(macos, f))

def resign():
    clean_bundle()
    print("[*] re-signing (ad-hoc, deep, no runtime hardening)…")
    sh("xattr", "-cr", APP)
    fw = os.path.join(APP, "Contents/Frameworks")
    if os.path.isdir(fw):
        for name in sorted(os.listdir(fw)):
            p = os.path.join(fw, name)
            if name.endswith(".framework") or name.endswith(".dylib"):
                sh("codesign", "--force", "--sign", "-", p)
    sh("codesign", "--force", "--sign", "-", BIN)
    sh("codesign", "--force", "--deep", "--sign", "-", APP)
    sh("codesign", "--verify", "--deep", "--strict", APP)

def main():
    if not os.path.exists(BIN):
        sys.exit(f"[-] not found: {BIN}")

    subprocess.run(["pkill", "-9", "Spokenly"])   # must not be running

    if not os.path.exists(ORIG):                  # capture pristine bytes once
        shutil.copy2(BIN, ORIG)
        print(f"[*] saved pristine copy → {ORIG}")

    shutil.copy2(ORIG, BIN)                        # always patch from clean → idempotent
    data = bytearray(open(BIN, "rb").read())

    hits = 0
    for off, size in arm64_ranges(data):
        i = data.find(PATTERN, off, off + size)
        while i != -1:
            p = i + PATCH_OFFSET_IN_PATTERN
            data[p:p+len(PATCH)] = PATCH
            hits += 1
            print(f"[+] patched arm64 @ file offset 0x{p:x}")
            i = data.find(PATTERN, i + len(PATTERN), off + size)

    if hits == 0:
        sys.exit("[-] pattern not found (app updated/changed?) — binary left pristine")
    if hits > 1:
        print(f"[!] {hits} matches patched — unexpected but harmless")

    open(BIN, "wb").write(data)
    print(f"[+] wrote {hits} patch(es)")
    resign()
    print("done. Launch it (as your user, NOT sudo):")
    print("     open /Applications/Spokenly.app")

if __name__ == "__main__":
    main()