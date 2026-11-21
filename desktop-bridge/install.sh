#!/usr/bin/env bash
# Install the OMNIBRIDGE Desktop Bridge native messaging host (macOS/Linux).
set -euo pipefail
HOST_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST_JS="$HOST_DIR/host.js"
chmod +x "$HOST_JS"

case "$(uname -s)" in
  Darwin)
    CHROME_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
    FIREFOX_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
    ;;
  Linux)
    CHROME_DIR="$HOME/.config/google-chrome/NativeMessagingHosts"
    FIREFOX_DIR="$HOME/.mozilla/native-messaging-hosts"
    ;;
  *)
    echo "Unsupported OS. On Windows, copy com.omnibridge.host.json to %APPDATA%\\Google\\Chrome\\NativeMessagingHosts and set path to host.js (run with node)."
    exit 1
    ;;
esac

mkdir -p "$CHROME_DIR" "$FIREFOX_DIR"
sed "s|REPLACE_WITH_ABSOLUTE_PATH_TO_host.js|$HOST_JS|" "$HOST_DIR/com.omnibridge.host.json" > "$CHROME_DIR/com.omnibridge.host.json"
cp "$CHROME_DIR/com.omnibridge.host.json" "$FIREFOX_DIR/com.omnibridge.host.json"
echo "Installed. Now load the extension from ../extension (chrome://extensions → Developer mode → Load unpacked),"
echo "note its ID, and replace REPLACE_WITH_EXTENSION_ID in the installed manifest."
