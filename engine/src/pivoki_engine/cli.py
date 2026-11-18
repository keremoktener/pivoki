import argparse
import json
import signal
import sys

from . import __version__
from .model import DEFAULT, Problem
from .service import dispatch


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def add_run_args(parser):
    parser.add_argument("--input", action="extend", nargs="+", required=True, metavar="FILE_OR_FOLDER")
    parser.add_argument("--out", required=True, metavar="DIRECTORY")
    parser.add_argument("--recursive", action="store_true", help="Include files in ordinary subfolders")
    parser.add_argument("--on-conflict", choices=["keep-both", "skip"], default="keep-both")
    parser.add_argument("--dry-run", action="store_true", help="Compute the exact paths before writing anything")
    parser.add_argument("--json", action="store_true")


def arguments():
    p = Parser(prog="pivoki", description="Pivoki local file processing", epilog=(
        f"Example: pivoki package run {DEFAULT} --revision 1 --input photo.png "
        "--out Delivery --on-conflict keep-both --dry-run --json"))
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--json", action="store_true")
    subs = p.add_subparsers(dest="command", required=True)
    for name in ("catalog", "dependencies", "packages", "history"):
        subs.add_parser(name).add_argument("--json", action="store_true")
    inspect = subs.add_parser("inspect")
    inspect.add_argument("files", nargs="*")
    inspect.add_argument("--input", nargs="+")
    inspect.add_argument("--json", action="store_true")
    pkg = subs.add_parser("package").add_subparsers(dest="verb", required=True)
    pkg.add_parser("list").add_argument("--json", action="store_true")
    run = pkg.add_parser("run", epilog=p.epilog)
    run.add_argument("package_id")
    run.add_argument("--revision", type=int)
    add_run_args(run)
    resize = subs.add_parser("tool").add_subparsers(dest="tool", required=True).add_parser("resize")
    for convert in [subs.add_parser("convert"), resize]:
        convert.add_argument("--format", choices=["png", "jpg", "jpeg", "webp"], required=True)
        convert.add_argument("--max-edge", type=int, default=65535)
        add_run_args(convert)
    studio = subs.add_parser("studio", help="Open the desktop file tools")
    studio.add_argument("paths", nargs="*")
    watch = subs.add_parser("watch", help="Process enabled folder rules until the host exits")
    watch.add_argument("--parent-pid", type=int, required=True)
    subs.add_parser("rpc", help="Read one JSON request on stdin and emit one JSON response")
    return p


def execute(args, check):
    if args.command == "rpc":
        try:
            req = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise UsageError(f"Invalid JSON: {exc}") from exc
        return dispatch(req, check)
    if args.command in ("catalog", "dependencies", "packages", "history"):
        return dispatch({"action": args.command}, check)
    if args.command == "inspect":
        return dispatch({"action": "inspect", "inputs": (args.input or []) + args.files}, check)
    if args.command == "package" and args.verb == "list":
        return dispatch({"action": "packages"}, check)

    request = {"action": "plan", "inputs": args.input, "outputRoot": args.out,
               "recursive": args.recursive, "conflictPolicy": args.on_conflict}
    if args.command == "package":
        request.update(packageId=args.package_id, revision=args.revision)
    else:
        request["package"] = {"name": "Pivoki", "outputs": [
            {"format": args.format, "maxEdge": args.max_edge, "relativeDir": ""}]}
    # A CLI invocation supplies an unattended conflict policy. Re-plan if publication lost a race.
    for _ in range(8):
        preview = dispatch(request, check)
        if preview["status"] != "planned" or args.dry_run:
            return preview
        result = dispatch({"action": "run", "planId": preview["planId"]}, check)
        if result.get("code") != "replan_required":
            return result
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    json_output = "rpc" in argv or "--json" in argv
    try:
        args = arguments().parse_args(argv)
        if args.command in ("studio", "watch"):
            try:
                if args.command == "studio":
                    from pivoki_studio import launch
                    return launch(args.paths) or 0
                from pivoki_studio.rules import serve
                return serve(args.parent_pid) or 0
            except ImportError as exc:
                raise UsageError(f"Install the Pivoki Studio package to use {args.command}: {exc}") from exc
        stopped = False

        def stop(_signum, _frame):
            nonlocal stopped
            stopped = True

        def check():
            if stopped:
                raise Problem("cancelled", "The operation was cancelled.")

        saved = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            result = execute(args, check)
        finally:
            for sig, prev in saved.items():
                signal.signal(sig, prev)
        status = result["status"]
        code = 130 if status == "cancelled" else 1 if status == "failed" else 0
    except UsageError as exc:
        result, code = {"status": "failed", "code": "usage", "error": str(exc)}, 64
    except KeyboardInterrupt:
        result, code = {"status": "cancelled", "code": "cancelled", "error": "Interrupted."}, 130
    if json_output:
        # JSON stays UTF-8 even on a Windows host with a legacy console code page.
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    elif code:
        print(result["error"], file=sys.stderr)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return code
