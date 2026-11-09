"""Extract the data track of a Sega Saturn BIN/CUE dump.

Usage: python -I extract_disc.py <track01.bin> <out_dir>

Writes:
  out_dir/track01.iso      data track as plain 2048-byte sectors
  out_dir/IP.BIN           system area (first 16 sectors: boot header + boot code)
  out_dir/ip_header.json   parsed boot header
  out_dir/files/...        every file in the ISO 9660 filesystem
  out_dir/manifest.json    file list with start sector (LBA) and size

The input file is only read, never modified.
"""
import json
import struct
import sys
from pathlib import Path

RAW = 2352
USER = 2048
SYNC = bytes([0x00] + [0xFF] * 10 + [0x00])


def to_iso(bin_path, iso_path):
    size = bin_path.stat().st_size
    if size % RAW:
        sys.exit(f"{bin_path} is not a whole number of 2352-byte sectors")
    count = size // RAW
    bad = 0
    with open(bin_path, "rb") as src, open(iso_path, "wb") as dst:
        for _ in range(count):
            s = src.read(RAW)
            if s[:12] != SYNC:
                bad += 1
            mode = s[15]
            if mode == 1:
                dst.write(s[16:16 + USER])
            elif mode == 2:  # Mode 2 Form 1
                dst.write(s[24:24 + USER])
            else:
                dst.write(bytes(USER))
                bad += 1
    return count, bad


def parse_ip(ip):
    def text(a, b):
        return " ".join(ip[a:b].decode("ascii", "replace").split())

    def u32(o):
        return f"0x{struct.unpack_from('>I', ip, o)[0]:08X}"

    return {
        "hardware_id": text(0x00, 0x10),
        "maker_id": text(0x10, 0x20),
        "product_number": text(0x20, 0x2A),
        "version": text(0x2A, 0x30),
        "release_date": text(0x30, 0x38),
        "device_info": text(0x38, 0x40),
        "area_codes": text(0x40, 0x4A),
        "peripherals": text(0x50, 0x60),
        "title": text(0x60, 0xD0),
        "ip_size": u32(0xE0),
        "master_stack": u32(0xE8),
        "slave_stack": u32(0xEC),
        "first_read_address": u32(0xF0),
        "first_read_size": u32(0xF4),
    }


def read_at(iso, lba, length):
    iso.seek(lba * USER)
    return iso.read(length)


def walk(iso, lba, size, rel, out_files, manifest, seen):
    if lba in seen:
        return
    seen.add(lba)
    data = read_at(iso, lba, size)
    pos = 0
    while pos < len(data):
        n = data[pos]
        if n == 0:  # records never cross a sector boundary; skip padding
            pos = (pos // USER + 1) * USER
            continue
        rec = data[pos:pos + n]
        pos += n
        extent = struct.unpack_from("<I", rec, 2)[0]
        length = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        raw_name = rec[33:33 + rec[32]]
        if raw_name in (b"\x00", b"\x01"):  # "." and ".."
            continue
        name = raw_name.decode("ascii", "replace").split(";")[0]
        if not name or name in (".", "..") or any(c in name for c in '/\\:'):
            sys.exit(f"Refusing unsafe file name {name!r}")
        path = rel + [name]
        dest = out_files.joinpath(*path)
        if flags & 0x02:
            dest.mkdir(parents=True, exist_ok=True)
            walk(iso, extent, length, path, out_files, manifest, seen)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read_at(iso, extent, length))
            manifest.append({"path": "/".join(path), "lba": extent, "size": length})


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    bin_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    iso_path = out / "track01.iso"
    count, bad = to_iso(bin_path, iso_path)

    with open(iso_path, "rb") as iso:
        ip = iso.read(16 * USER)
        (out / "IP.BIN").write_bytes(ip)
        header = parse_ip(ip)
        pvd = read_at(iso, 16, USER)
        if pvd[1:6] != b"CD001":
            sys.exit("No ISO 9660 volume descriptor at sector 16")
        header["volume_id"] = pvd[40:72].decode("ascii", "replace").strip()
        root = pvd[156:156 + 34]
        root_lba = struct.unpack_from("<I", root, 2)[0]
        root_len = struct.unpack_from("<I", root, 10)[0]
        files = out / "files"
        files.mkdir(exist_ok=True)
        manifest = []
        walk(iso, root_lba, root_len, [], files, manifest, set())

    header["first_read_file"] = next(
        (m["path"] for m in manifest if "/" not in m["path"]), None)
    (out / "ip_header.json").write_text(json.dumps(header, indent=2))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    total = sum(m["size"] for m in manifest)
    print(f"sectors: {count}, sectors with bad sync/mode: {bad}")
    print(f"files: {len(manifest)}, total {total:,} bytes")
    for k, v in header.items():
        print(f"{k}: {v}")
    print("largest files:")
    for m in sorted(manifest, key=lambda m: -m["size"])[:10]:
        print(f"  {m['path']:<24} {m['size']:>10,}  lba {m['lba']}")


if __name__ == "__main__":
    main()
