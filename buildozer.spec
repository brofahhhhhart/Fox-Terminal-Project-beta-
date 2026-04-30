[app]

# (str) Title of your application
title = Fox Terminal

# (str) Package name
package.name = foxterminal

# (str) Package domain (needed for android/ios packaging)
package.domain = org.foxterminal

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json

# (str) Application versioning
version = 1.30.0

# (list) Application requirements
requirements = python3,kivy==2.3.1,kivymd==2.0.1,materialyoucolor,exceptiongroup,asyncgui,asynckivy,pillow,requests,urllib3,charset-normalizer,idna,certifi

# (str) Presplash of the application
presplash.filename = %(source.dir)s/presplash.png

# (str) Icon of the application
icon.filename = %(source.dir)s/icon.png

# (str) Supported orientation
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (str) Presplash background color
android.presplash_color = #141416

#
# Android specific
#

# (list) Permissions
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# (int) Target Android API
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 21

# (int) Android NDK API to use
android.ndk_api = 21

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Accept SDK license agreement automatically
android.accept_sdk_license = True

# (list) The Android archs to build for
android.archs = arm64-v8a

# (bool) enables Android auto backup feature
android.allow_backup = True

# (str) Bootstrap to use for android builds
p4a.bootstrap = sdl2

# (str) python-for-android branch to use (develop has AAB support)
p4a.branch = develop

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
