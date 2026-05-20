#!/bin/zsh
# Download Lucide SVG icons from https://lucide.dev/icons/
# MIT Licensed. Just paste the icon name below.
curl -sL "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/${1}.svg" -o "${1}.svg" 2>/dev/null

# Or use this python one-liner:
# python3 -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/INBOX.svg', 'inbox.svg')"
