[app]

title = FourWay TD
package.name = fourwaytd
package.domain = org.fourway
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.exclude_patterns = desktop_main.py,tower.py,enemy.py,bullet.py,const.py,grid.py,groups.py,docs/*,.github/*,*.ipynb,.git/*
version = 0.2
# Pin host + target Python to the same version (p4a requires them to match).
requirements = hostpython3==3.11.13,python3==3.11.13,kivy==2.3.1
orientation = portrait
fullscreen = 1
android.permissions = INTERNET
# entrypoint defaults to main.py

android.archs = arm64-v8a
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.allow_backup = True
android.logcat_filters = *:S python:D

# Match kivy CI; more resilient recipe set on current Ubuntu runners.
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
