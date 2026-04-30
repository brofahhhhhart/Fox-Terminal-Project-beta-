# ════════════════════════════════════════════════════════════════
#  Fox Terminal — buildozer.spec
#  Coloque na RAIZ do repositorio (mesma pasta do main.py)
#
#  ATENCAO: KivyMD 2.0.1 foi trocado por 1.2.0
#  O motivo: KivyMD 2.x nao compila em aarch64 com p4a/sdl2.
#  Todos os imports do main.py ja sao compativeis com 1.2.0.
#
#  presplash.png foi removido dos requirements porque o arquivo
#  nao existe no repo. O icon.png e usado como splash.
# ════════════════════════════════════════════════════════════════

[app]

# Nome que aparece no celular
title = Fox Terminal

# Nome do pacote (unico, estilo Java — nao mude depois de publicar)
package.name = foxterminal

# Dominio do pacote
package.domain = org.foxterminal

# Pasta do codigo fonte
source.dir = .

# Extensoes de arquivo incluidas no APK
source.include_exts = py,png,jpg,kv,atlas,json

# Versao do app (atualize a cada build)
version = 1.34.0

# ─── Dependencias ────────────────────────────────────────────────
# IMPORTANTE:
#  - Cython==0.29.33 e obrigatorio (Cython 3.x quebra kivy 2.x)
#  - KivyMD 1.2.0 e a versao estavel que compila em aarch64
#  - materialyoucolor, asyncgui, asynckivy removidos:
#    sao dependencias do KivyMD 2.x, nao existem no 1.2.0
#  - exceptiongroup: opcional, nao afeta o app
requirements =
    python3==3.11.8,
    kivy==2.3.1,
    kivymd==1.2.0,
    Cython==0.29.33,
    pillow,
    certifi

# ─── Icone e Splash ───────────────────────────────────────────────
icon.filename = %(source.dir)s/icon.png

# Cor de fundo da tela de loading (enquanto o APK inicializa)
android.presplash_color = #141416

# ─── Orientacao e interface ───────────────────────────────────────
orientation = portrait
fullscreen = 0

# ─── Permissoes Android ───────────────────────────────────────────
android.permissions =
    INTERNET,
    WRITE_EXTERNAL_STORAGE,
    READ_EXTERNAL_STORAGE,
    ACCESS_NETWORK_STATE

# ─── API e NDK ────────────────────────────────────────────────────
# API alvo
android.api = 33

# API minima (Android 5.0+)
android.minapi = 21

# NDK r25b e o mais estavel com python-for-android atual
android.ndk = 25b
android.ndk_api = 21

# Aceita licenca do SDK automaticamente (obrigatorio no CI)
android.accept_sdk_license = True

# ─── Arquiteturas ─────────────────────────────────────────────────
# arm64-v8a  = celulares modernos (maioria dos Android atuais)
# armeabi-v7a = celulares mais antigos (adicione se quiser mais compatibilidade)
android.archs = arm64-v8a

# ─── Armazenamento e backup ────────────────────────────────────────
android.private_storage = True
android.allow_backup = True

# ─── Bootstrap ────────────────────────────────────────────────────
p4a.bootstrap = sdl2

# Branch estavel do python-for-android
p4a.branch = stable

# ─── Gradle / SDK ─────────────────────────────────────────────────
android.build_tools_version = 33.0.2

# ─── Log ──────────────────────────────────────────────────────────
[buildozer]
log_level = 2
warn_on_root = 1
