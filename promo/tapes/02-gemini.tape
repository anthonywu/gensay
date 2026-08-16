# Scene: Gemini TTS provider — 30 prebuilt voices, multi-speaker dialogue
Output remotion/public/clips/02-gemini.mp4

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

Type "gensay -p gemini -v '?' | head -24"
Sleep 500ms
Enter
Wait
Sleep 2s

Type "gensay -p gemini -v 'Joe=Kore,Jane=Puck' -f dialogue.txt"
Sleep 2.5s
