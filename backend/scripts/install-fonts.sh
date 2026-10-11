#!/bin/sh
# Install the export fonts listed in backend/fonts/google-fonts.sha256 and the
# fontconfig aliases beside it. Run during the image build, from the directory
# holding fonts/. Fails the build if any download or checksum does not match.
set -eu
here=$(dirname "$0")/..
manifest="$here/fonts/google-fonts.sha256"
base=$(sed -n 's/^# source: //p' "$manifest")
dest=/usr/share/fonts/truetype/typecast
work=$(mktemp -d)
mkdir -p "$dest"

grep -v '^#' "$manifest" | grep -v '^$' | while read -r sum path; do
  url="$base$(printf '%s' "$path" | sed 's/\[/%5B/g; s/\]/%5D/g')"
  mkdir -p "$work/$(dirname "$path")"
  curl -fsSL --retry 3 -o "$work/$path" "$url"
done
(cd "$work" && grep -v '^#' "$manifest" | grep -v '^$' | sha256sum -c --quiet -)

# Fonts flat in one directory; each licence kept beside its family's name.
find "$work" -name '*.ttf' -exec cp {} "$dest/" \;
for licence in "$work"/*/OFL.txt; do
  cp "$licence" "$dest/$(basename "$(dirname "$licence")")-OFL.txt"
done
cp "$here/fonts/60-typecast-aliases.conf" /etc/fonts/conf.d/60-typecast-aliases.conf
rm -rf "$work"
fc-cache -f >/dev/null
echo "Installed $(ls "$dest"/*.ttf | wc -l) font files into $dest"
