#!/usr/bin/env python3
"""Read the TouchDesigner side of the bridge through the project webserver.

TouchDesigner's lira.20.toe ships an MCP webserver on 127.0.0.1:9981. This
talks to that server, so the Datamoshing bindings and the picture are provable
without a TouchDesigner MCP client.

The server runs the script inside TouchDesigner and returns its result. Two
traps shape the scripts this sends:

- The serializer sends every non-scalar through td.op(), so a nested dict
  comes back as a node summary. Return flat scalars: numbers, strings, or a
  flat list of them.
- A script that never sets `result` gets its last line evaluated again, so a
  trailing `main()` call runs twice. Set `result` explicitly or end on a
  plain expression.

  exec <script-or-file>   POST a script and print the JSON response
  par   <path> <name>     read one parameter's value and mode
  chans <path>            list the channel names on a CHOP
  top   <path> <file>     capture a TOP's output to a PNG
"""

import argparse
import base64
import json
import sys
import urllib.request

try:
    from PIL import Image
    import numpy as np
except ImportError:  # pragma: no cover - the top command needs both
    Image = None
    np = None

API = "http://127.0.0.1:9981/api/td/server/exec"


def exec_script(script):
    body = json.dumps({"script": script}).encode()
    request = urllib.request.Request(API, data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def require_ok(parsed):
    if not parsed.get("success"):
        raise SystemExit("FAIL: %s" % parsed.get("error", "server error"))
    return parsed.get("data", {})


def cmd_exec(args):
    script = args.script
    if args.file:
        with open(args.file) as handle:
            script = handle.read()
    parsed = exec_script(script)
    require_ok(parsed)
    print(json.dumps(parsed["data"], indent=2))


def cmd_par(args):
    script = (
        "par = op(%r).par.%s\n"
        "result = [round(float(par.eval()), 4), str(par.mode).split('.')[-1]]"
        % (args.path, args.name))
    data = require_ok(exec_script(script))
    value, mode = data["result"]
    print("%s/%s mode=%s value=%s" % (args.path, args.name, mode, value))


def cmd_chans(args):
    script = ("result = [c.name for c in op(%r).chans()]" % args.path)
    data = require_ok(exec_script(script))
    for name in data["result"]:
        print(name)


def cmd_top(args):
    if Image is None or np is None:
        raise SystemExit("FAIL: top needs Pillow and numpy on the repo side")
    # TouchDesigner's .save() resolves against its own working directory, so
    # the pixels come back over the webserver instead and are written here.
    script = (
        "import numpy as np, base64\n"
        "top = op('" + args.path + "')\n"
        "if top.isCOMP:\n"
        "    top = top.outputs[0]\n"
        "top.cook(force=True)\n"
        "arr = top.numpyArray()\n"
        "if arr.dtype != np.uint8:\n"
        "    arr = np.clip(arr * 255, 0, 255).astype(np.uint8)\n"
        "result = '%dx%d,' % (arr.shape[1], arr.shape[0]) + "
        "base64.b64encode(arr.tobytes()).decode()"
    )
    data = require_ok(exec_script(script))
    header, _, b64 = data["result"].partition(",")
    width, height = map(int, header.split("x"))
    raw = base64.b64decode(b64)
    image = Image.frombytes("RGBA", (width, height), raw)
    image.save(args.file, "PNG")
    print("saved %s (%dx%d)" % (args.file, width, height))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("exec", help="POST a script and print the JSON response")
    p.add_argument("script", nargs="?", help="script text, or use --file")
    p.add_argument("--file", help="read the script from this file")
    p.set_defaults(func=cmd_exec)

    p = sub.add_parser("par", help="read one parameter's value and mode")
    p.add_argument("path")
    p.add_argument("name")
    p.set_defaults(func=cmd_par)

    p = sub.add_parser("chans", help="list the channel names on a CHOP")
    p.add_argument("path")
    p.set_defaults(func=cmd_chans)

    p = sub.add_parser("top", help="capture a TOP's output to a PNG")
    p.add_argument("path")
    p.add_argument("file")
    p.set_defaults(func=cmd_top)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())