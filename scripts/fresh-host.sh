#!/bin/sh
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd -P)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone -q --no-hardlinks "$repo" "$work/jstack"
cp "$repo/.cursor/skills/verify-jstack/scripts/fake-systemctl" "$work/systemctl"

docker run --rm -i -v "$work:/src:ro" archlinux:latest sh -eu << 'IN_THE_CONTAINER'
pacman -Sy --noconfirm --needed uv git jq findutils diffutils > /dev/null
stand=/opt/stand-in
mkdir -p "$stand"
printf '#!/bin/sh\necho "t3 v0.0.46-nightly.20261015.3158"\n' > "$stand/t3"
printf '#!/bin/sh\necho "2.1.296 (Claude Code)"\n' > "$stand/claude"
printf '#!/bin/sh\n[ "$1 $2" = "auth token" ] && echo gho_stand_in\n' > "$stand/gh"
printf '#!/bin/sh\nexit 0\n' > "$stand/lavish-axi"
cp /src/systemctl "$stand/systemctl"
chmod 755 "$stand"/*
export PATH="$stand:$HOME/.local/bin:$PATH" FAKE_SYSTEMCTL_LOG=/tmp/systemctl.log
cp -a /src/jstack "$HOME/jstack"
cd "$HOME/jstack"

echo "== sh install.sh --setup"
code=0
sh install.sh --setup > /tmp/first || code=$?
cat /tmp/first
echo "exit $code"
echo "== sh install.sh --doctor"
sh install.sh --doctor > /tmp/doctor || true
tail -n 1 /tmp/doctor
find "$HOME" -path "$HOME/.cache" -prune -o -print | sort > /tmp/before
record=$(cat "$HOME/.local/state/jstack/created" "$HOME/.local/state/jstack/seeded" | sha256sum)
echo "== sh install.sh --setup, again"
second=0
sh install.sh --setup > /tmp/second || second=$?
grep -v '^already ' /tmp/second
find "$HOME" -path "$HOME/.cache" -prune -o -print | sort > /tmp/after

fail=
[ "$code" = 0 ] || fail="$fail; the first --setup exited $code"
[ "$second" = 0 ] || fail="$fail; the second --setup exited $second"
[ "$(tail -n 1 /tmp/doctor)" = "doctor: ok" ] || fail="$fail; the doctor is not ok"
grep -v '^already \|^needs you ' /tmp/second && fail="$fail; the second run wrote something"
diff /tmp/before /tmp/after || fail="$fail; the second run changed the files under HOME"
[ "$record" = "$(cat "$HOME/.local/state/jstack/created" "$HOME/.local/state/jstack/seeded" | sha256sum)" ] ||
    fail="$fail; the records changed"
left=$(sed -n '/^needs you state repo /d; s/^needs you .* -> //p' /tmp/second | sort | paste -sd, -)
[ "$left" = "claude,jbus t3 login" ] || fail="$fail; needs you left: $left"
if [ -n "$fail" ]; then
    echo "fresh host: failed${fail}"
    exit 1
fi
echo "fresh host: ok, doctor: ok, the second run wrote nothing, left: $left"
IN_THE_CONTAINER
