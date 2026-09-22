#!/usr/bin/env python3
"""Round-trip check for the LIRA-8 OSC bridge.

Launches a throwaway patch that instantiates `av.osc` the same way `_LIRA-8.pd`
does, then asserts both directions against real UDP traffic:

  out  LIRA bus  ->  /lira/<name> datagram
  in   /lira/<name> datagram  ->  LIRA bus

The cases cover a bus the widgets publish, a numbered one, and one the engine
only publishes, so both halves of the naming convention are exercised. The
check talks only OSC, so it stays valid if the bridge is reimplemented.
"""

import argparse
import os
import socket
import struct
import subprocess
import sys
import threading
import time

ID = 12345
OUT_PORT = 9121
IN_PORT = 9122

# base name -> value the probe publishes on that bus. cpu and led are live
# readouts the engine owns, the rest are controls.
OUTBOUND = (("vol", 11), ("mod-12", 22), ("led", 33), ("cpu", 44))
# base name -> value the probe should receive back
INBOUND = (("vol", 101), ("mod-12", 202), ("drv", 303))
# Where the probe has to publish to reach each outbound bus. Anything the
# widgets own is published on s-, engine status on r-.
OUT_SOURCE = {"vol": "s-vol", "mod-12": "s-mod-12", "led": "r-led",
              "cpu": "r-cpu"}
# Where the bridge should deliver each inbound address.
IN_TARGET = {"vol": "r-vol", "mod-12": "r-mod-12", "drv": "r-drv"}
# Buses the patch publishes on a bare global, with no $0 prefix.
GLOBAL = set()


def osc_message(address, value):
    def pad(raw):
        # A string is null-terminated and then padded, so a 4-aligned string
        # still gains a whole null word.
        return raw + b"\x00" * (4 - len(raw) % 4)

    return pad(address.encode()) + pad(b",i") + struct.pack(">i", value)


def parse_osc(data):
    def read_string(buf, start):
        end = buf.index(b"\x00", start)
        return buf[start:end].decode(), (end + 4) & ~3

    address, offset = read_string(data, 0)
    if offset >= len(data):
        return address, []
    tags, offset = read_string(data, offset)
    values = []
    for tag in tags[1:]:
        if tag == "i":
            values.append(struct.unpack_from(">i", data, offset)[0])
            offset += 4
        elif tag == "f":
            values.append(struct.unpack_from(">f", data, offset)[0])
            offset += 4
    return address, values


def test_patch():
    lines = [
        "#N canvas 0 0 900 700 12;",
        "#X obj 40 40 loadbang;",
        "#X obj 40 70 del 900;",
        f"#X obj 40 220 av.osc {ID};",
    ]
    index = 3
    wiring = ["#X connect 0 0 1 0;"]

    def add(text):
        nonlocal index
        lines.append(f"#X obj {40 + 20 * index} {100 + 20 * index} {text};")
        index += 1
        return index - 1

    for base, value in OUTBOUND:
        driver = add(f"s {ID}-{OUT_SOURCE[base]}")
        msg = add(str(value))
        wiring.append(f"#X connect 1 0 {msg} 0;")
        wiring.append(f"#X connect {msg} 0 {driver} 0;")

    for base, _ in INBOUND:
        target = IN_TARGET[base]
        name = target if target in GLOBAL else f"{ID}-{target}"
        recv = add(f"r {name}")
        printer = add(f"print RECV {base}")
        wiring.append(f"#X connect {recv} 0 {printer} 0;")

    return "\n".join(lines + wiring) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook", default="abs", help="directory holding av.osc.pd")
    args = parser.parse_args()

    hook = os.path.abspath(args.hook)
    if not os.path.isfile(os.path.join(hook, "av.osc.pd")):
        print(f"FAIL: no av.osc.pd in {hook}")
        return 1

    patch_path = os.path.join(hook, "_verify_osc_probe.pd")
    with open(patch_path, "w") as handle:
        handle.write(test_patch())

    outbound = []
    out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    out_sock.bind(("127.0.0.1", OUT_PORT))
    out_sock.settimeout(1.0)

    def collect():
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                data, _ = out_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                outbound.append(parse_osc(data))
            except (ValueError, IndexError):
                outbound.append(("unparseable", []))

    threading.Thread(target=collect, daemon=True).start()

    proc = subprocess.Popen(
        ["pd", "-nogui", "-noaudio", "-path", hook, patch_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    stdout = []

    def drain():
        for line in proc.stdout:
            stdout.append(line.rstrip())

    threading.Thread(target=drain, daemon=True).start()

    time.sleep(3.0)
    inbound = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for base, value in INBOUND:
        inbound.sendto(osc_message(f"/lira/{base}", value),
                       ("127.0.0.1", IN_PORT))
        # netreceive -u -b coalesces datagrams that land in the same poll, and
        # oscparse then sees one malformed message instead of several good
        # ones, so the sends are spaced.
        time.sleep(0.4)
    time.sleep(3.0)

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    os.unlink(patch_path)
    out_sock.close()

    problems = []
    for base, value in OUTBOUND:
        got = [v for addr, v in outbound if addr == f"/lira/{base}"]
        if not any(v and int(v[0]) == value for v in got):
            problems.append(f"no /lira/{base} carrying {value}")
    for base, value in INBOUND:
        if not any(f"RECV {base}: {value}" in line for line in stdout):
            problems.append(f"pd never received /lira/{base} value {value}")

    print(f"outbound datagrams: {outbound or 'none'}")
    print(f"pd stdout: {stdout or 'empty'}")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(f"PASS: {len(OUTBOUND)} buses out, {len(INBOUND)} buses in, all verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
