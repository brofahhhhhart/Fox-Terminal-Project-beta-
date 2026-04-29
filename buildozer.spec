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
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,android

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (str) Presplash background color
android.presplash_color = #141416

#
# Android specific
#

# (list) Application requirements
requirements = python3,kivy==2.3.1,kivymd>=2.0.0,pillow,requests,urllib3,android

# (list) Permissions
android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES, READ_MEDIA_VIDEO

# (int) Target Android API
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 21

# (bool) Accept SDK license agreement automatically
android.accept_sdk_license = True

# (list) The Android archs to build for
android.archs = arm64-v8a

# (bool) enables Android auto backup feature
android.allow_backup = True

# (str) Bootstrap to use for android builds
p4a.bootstrap = sdl2

# (bool) Use --private data storage (True) or --dir public storage (False)
android.private_storage = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
