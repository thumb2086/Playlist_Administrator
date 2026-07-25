import os, re, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
d = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')
for name in sorted(os.listdir(d)):
    p = os.path.join(d, name)
    if os.path.isdir(p):
        n = len([f for f in os.listdir(p) if f.endswith('.mp3')])
        print(f'{name}: {n}')
