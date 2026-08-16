# Scene: drop-in replacement for macOS `say`
Output remotion/public/clips/01-say.mp4

Set Shell bash
Set FontSize 26
Set Width 1600
Set Height 900
Set Padding 40
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set WindowBar Colorful
Set BorderRadius 12

# Clean-slate config so personal defaults don't leak into the recording
Env GENSAY_CONFIG "/tmp/gensay-sizzle-noconfig.toml"

Hide
Type "cd /tmp && clear"
Enter
Show

Type "gensay -p macos 'It is 2026. Your terminal can talk.'"
Sleep 500ms
Enter
# Wait for the prompt to return (speech blocks) before typing the next command
Wait
Sleep 1s

Type "gensay -p macos -o hello.mp3 'Or save it for later.'"
Sleep 500ms
Enter
Wait
Sleep 1.5s
