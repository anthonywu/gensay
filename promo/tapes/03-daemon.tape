# Scene: warm inference daemon — keep local AI models loaded
Output remotion/public/clips/03-daemon.mp4

Set Shell bash
Set FontSize 26
Set Width 1600
Set Height 900
Set Padding 40
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set WindowBar Colorful
Set BorderRadius 12

Env GENSAY_RUNTIME_DIR "/tmp/gensay-sizzle-runtime"
Env GENSAY_SOCKET "/tmp/gensay-sizzle-runtime/s.sock"
# Clean-slate config so personal defaults don't leak into the recording
Env GENSAY_CONFIG "/tmp/gensay-sizzle-noconfig.toml"

Hide
Type "mkdir -p /tmp/gensay-sizzle-runtime && cd /tmp && clear"
Enter
Show

Type "gensay daemon start -p mock"
Sleep 500ms
Enter
Wait
Sleep 1s

Type "gensay daemon status"
Sleep 300ms
Enter
Wait
Sleep 1.5s

Type "gensay -p mock --via-daemon 'model stays warm — speech is instant'"
Sleep 500ms
Enter
Wait
Sleep 1.5s

Hide
Type "gensay daemon stop"
Enter
Sleep 1s
Show

Sleep 500ms
