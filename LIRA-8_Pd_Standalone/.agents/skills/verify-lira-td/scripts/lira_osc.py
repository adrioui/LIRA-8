#!/usr/bin/env python3
"""Drive and observe the LIRA-8 OSC bridge on the wire.

Pd publishes every instrument bus to 127.0.0.1:9121 as /lira/<name>, and
accepts the writable ones on 127.0.0.1:9122. This talks that wire directly, so
the Pd half of the bridge is provable without the GUI.

Nothing here touches TouchDesigner. When TouchDesigner owns 9121 the bind
fails on purpose, because observing the bridge then means reading the lira_osc
CHOP through the TouchDesigner MCP instead.

  doctor     report whether the surfaces a run needs are present
  listen     bind the Pd output port and list what arrives
  send       write one address to the Pd input port
  roundtrip  write a writable bus and require Pd to echo it back
"""

import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time

OUT_PORT = 9121      # Pd sends here, TouchDesigner's lira_osc listens here
IN_PORT = 9122       # Pd listens here
TD_API_PORT = 9981   # TouchDesigner MCP webserver


def encode_int(address, value):
    def pad(raw):
        # A string is null-terminated and then padded, so a 4-aligned string
        # still gains a whole null word.
        return raw + b"\x00" * (4 - len(raw) % 4)

    return pad(address.encode()) + pad(b",i") + struct.pack(">i", value)


def decode(data):
    def read_string(buf, start):
        end = buf.index(b"\x00", start)
        return buf[start:end].decode("utf-8", "replace"), (end + 4) & ~3

    address, offset = read_string(data, 0)
    values = []
    if offset < len(data):
        tags, offset = read_string(data, offset)
        for tag in tags[1:]:
            if tag == "i":
                values.append(struct.unpack_from(">i", data, offset)[0])
                offset += 4
            elif tag == "f":
                values.append(round(struct.unpack_from(">f", data, offset)[0], 4))
                offset += 4
    return address, values


def bind_listener(port):
    """Bind without SO_REUSEADDR so a port already owned by someone fails loudly."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        sock.close()
        raise SystemExit(
            "FAIL: cannot bind 127.0.0.1:%d (%s). Another process owns it, "
            "so this is not a clean instance to drive." % (port, exc))
    return sock


def collect(sock, seconds):
    seen = []
    deadline = time.time() + seconds
    sock.settimeout(0.5)
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            address, values = decode(data)
        except (ValueError, IndexError):
            continue
        if values:
            seen.append((address, values[0]))
    return seen


def udp_owner(port):
    try:
        out = subprocess.run(["lsof", "-nP", "-iUDP:%d" % port],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            return parts[0]
    return None


def tcp_open(port):
    with socket.socket() as probe:
        probe.settimeout(1.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def td_running():
    try:
        return subprocess.run(["pgrep", "-f", "TouchDesigner.app"],
                              capture_output=True, text=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_pd():
    """pd lives on the Nix profile path here, which a bare /bin/sh does not carry."""
    found = shutil.which("pd")
    if found:
        return found
    for candidate in ("/run/current-system/sw/bin/pd", "/usr/local/bin/pd",
                      "/opt/homebrew/bin/pd", "/Applications/Pd.app/Contents/Resources/bin/pd"):
        if os.path.exists(candidate):
            return candidate
    return None


def cmd_doctor(args):
    pd_path = find_pd()
    owner_9121 = udp_owner(OUT_PORT)
    report = {
        "pd": pd_path,
        "touchdesigner_process": td_running(),
        "td_api_9981": tcp_open(TD_API_PORT),
        "udp_9121_owner": owner_9121,
        "udp_9122_owner": udp_owner(IN_PORT),
    }
    report["pd_lane_available"] = bool(pd_path) and owner_9121 != "pd"
    report["td_lane_available"] = report["td_api_9981"]
    print(json.dumps(report, indent=2))

    if not pd_path:
        print("FAIL: no pd on PATH; the bridge cannot be driven", file=sys.stderr)
        return 1
    if owner_9121 == "pd":
        print("FAIL: a pd already owns 9121; not driving a shared instance",
              file=sys.stderr)
        return 1
    return 0


def cmd_listen(args):
    sock = bind_listener(args.port)
    print("listening on 127.0.0.1:%d for %ss" % (args.port, args.seconds))
    seen = collect(sock, args.seconds)
    sock.close()

    for address, value in sorted(seen):
        print("%s %s" % (address, value))
    if args.save:
        with open(args.save, "w") as handle:
            for address, value in sorted(seen):
                handle.write("%s %s\n" % (address, value))
        print("wrote %s" % args.save)

    problems = []
    for want in args.expect:
        address, _, raw = want.partition("=")
        hit = [v for a, v in seen if a == address]
        if not hit:
            problems.append("no datagram for %s" % address)
        elif raw and not any(str(v) == raw for v in hit):
            problems.append("%s arrived as %s, expected %s" % (address, hit, raw))
    print("addresses seen: %d" % len({a for a, _ in seen}))
    if problems:
        for problem in problems:
            print("FAIL: %s" % problem)
        return 1
    print("PASS")
    return 0


def cmd_send(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(encode_int(args.address, args.value), ("127.0.0.1", args.port))
    sock.close()
    print("sent %s %s to 127.0.0.1:%d" % (args.address, args.value, args.port))
    return 0


def cmd_roundtrip(args):
    address = args.address
    if not address.startswith("/"):
        address = "/lira/" + address
    sock = bind_listener(args.out_port)

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender.sendto(encode_int(address, args.value), ("127.0.0.1", args.in_port))
    sender.close()
    print("sent %s %s to 127.0.0.1:%d" % (address, args.value, args.in_port))

    seen = collect(sock, args.seconds)
    sock.close()
    echoed = [v for a, v in seen if a == address]
    print("echoed back on %d: %s" % (args.out_port, echoed or "nothing"))
    if args.save:
        with open(args.save, "w") as handle:
            for a, v in sorted(seen):
                handle.write("%s %s\n" % (a, v))
    if args.value in echoed:
        print("PASS: Pd accepted %s and published it again" % address)
        return 0
    print("FAIL: %s did not come back carrying %s" % (address, args.value))
    return 1


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="report whether the surfaces are present")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("listen", help="bind the Pd output port and list datagrams")
    p.add_argument("--port", type=int, default=OUT_PORT)
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--expect", action="append", default=[],
                   metavar="ADDR[=VALUE]", help="assert this address arrives")
    p.add_argument("--save", help="write the address/value transcript here")
    p.set_defaults(func=cmd_listen)

    p = sub.add_parser("send", help="write one address to the Pd input port")
    p.add_argument("address")
    p.add_argument("value", type=int)
    p.add_argument("--port", type=int, default=IN_PORT)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("roundtrip", help="write a bus and require Pd to echo it")
    p.add_argument("address", help="bus name or /lira/<name>")
    p.add_argument("value", type=int)
    p.add_argument("--out-port", type=int, default=OUT_PORT)
    p.add_argument("--in-port", type=int, default=IN_PORT)
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--save")
    p.set_defaults(func=cmd_roundtrip)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
