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
import subprocess
import sys
import tempfile
import threading
import time

from osc_bridge_source import PATCH, scan_control_receivers, scan_engine_published
from osc_packet import decode, encode_int

ID = 12345
OUT_PORT = 9121
IN_PORT = 9122

ENGINE = scan_engine_published(PATCH)
WRITABLE = scan_control_receivers(PATCH)

# led and cpu are engine readouts, so the probe publishes them on r-.
# vol and mod-12 are read from s-. mod-12 has no r $0-s- receiver, so the
# inbound cases use mod-2, which the scan says is writable.
OUTBOUND = (("vol", 11), ("mod-12", 22), ("led", 33), ("cpu", 44))
INBOUND = (("vol", 101), ("mod-2", 202), ("drv", 303))


def source_name(base):
    side = "r" if base in ENGINE else "s"
    return "%s-%s" % (side, base)


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
        driver = add("s %s-%s" % (ID, source_name(base)))
        msg = add(str(value))
        wiring.append("#X connect 1 0 %d 0;" % msg)
        wiring.append("#X connect %d 0 %d 0;" % (msg, driver))

    for base, _ in INBOUND:
        recv = add("r %s-s-%s" % (ID, base))
        printer = add("print RECV %s" % base)
        wiring.append("#X connect %d 0 %d 0;" % (recv, printer))

    return "\n".join(lines + wiring) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook", default="abs", help="directory holding av.osc.pd")
    args = parser.parse_args()

    hook = os.path.abspath(args.hook)
    if not os.path.isfile(os.path.join(hook, "av.osc.pd")):
        print("FAIL: no av.osc.pd in %s" % hook)
        return 1
    missing = [base for base, _ in INBOUND if base not in WRITABLE]
    if missing:
        print("FAIL: not a control receiver: %s" % ", ".join(missing))
        return 1

    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".pd", prefix="lira_osc_probe_", delete=False)
    patch_path = handle.name
    handle.write(test_patch())
    handle.close()

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
                outbound.append(decode(data))
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
        inbound.sendto(encode_int("/lira/%s" % base, value),
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
