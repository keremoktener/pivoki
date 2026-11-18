#!/usr/bin/env bash
# Run inside an Xvfb host. Weston supplies the Wayland session and XWayland client server.
set -euo pipefail
runtime_dir="$(mktemp -d)"
export XDG_RUNTIME_DIR="$runtime_dir"
weston -B x11 --renderer=pixman --width=1380 --height=1000 --socket=wayland-pivoki \
    --xwayland --no-config --log="$runtime_dir/weston.log" >"$runtime_dir/compositor.log" 2>&1 &
compositor=$!
cleanup() {
    kill "$compositor" 2>/dev/null || true
    wait "$compositor" 2>/dev/null || true
    rm -rf "$runtime_dir"
}
trap cleanup EXIT
for _ in $(seq 1 100); do
    if [[ -f "$runtime_dir/weston.log" ]] && grep -q 'xserver listening on display' "$runtime_dir/weston.log"; then break; fi
    sleep 0.1
done
display="$(sed -n 's/.*xserver listening on display \(:[0-9][0-9]*\).*/\1/p' "$runtime_dir/weston.log" | head -1)"
if [[ -z "$display" ]]; then cat "$runtime_dir/weston.log" >&2; exit 1; fi
XDG_SESSION_TYPE=wayland WAYLAND_DISPLAY=wayland-pivoki DISPLAY="$display" "$@"
