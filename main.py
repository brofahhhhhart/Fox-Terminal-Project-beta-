"""
Fox Terminal v1.34.0
====================
Requer (buildozer.spec requirements):
  kivy==2.3.1, kivymd==1.2.0, requests, certifi

Firebase Auth usa apenas requests (sem firebase-admin, que nao compila em aarch64).
A autenticacao e feita pela REST API do Firebase Authentication.
"""
import sys
import io
import os
import re
import subprocess
import threading
import json
import zipfile
import shutil
import time

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivy.uix.screenmanager import ScreenManager, NoTransition, FadeTransition
from kivymd.uix.navigationdrawer import MDNavigationDrawer
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.list import MDList, OneLineIconListItem, IconLeftWidget
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.button import MDIconButton, MDRaisedButton
from kivymd.uix.label import MDLabel
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import AsyncImage
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import platform
from kivy.metrics import dp

Window.softinput_mode = 'pan'

VERSION = "v1.34.0"

# ─── Firebase REST API ────────────────────────────────────────────────────────
# Troque pela sua Web API Key do Firebase Console
# (Projeto > Configuracoes > Geral > Chave de API da Web)
FIREBASE_API_KEY = "AIzaSyCfnQlrZ1x3EL5QtcN2V1oo7FY_VIiDdMA"
FIREBASE_BASE    = "https://identitytoolkit.googleapis.com/v1/accounts"

# ─── Dados persistentes ───────────────────────────────────────────────────────
DATA_DIR     = None
HISTORY_FILE = None
MODS_FILE    = None
ALIAS_FILE   = None
ENV_FILE     = None
SESSION_FILE = None
EXPORT_DIR   = None

def _init_paths(data_dir: str):
    global DATA_DIR, HISTORY_FILE, MODS_FILE, ALIAS_FILE
    global ENV_FILE, SESSION_FILE, EXPORT_DIR
    DATA_DIR = data_dir
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Arquivos internos (Sempre funcionam)
    HISTORY_FILE = os.path.join(DATA_DIR, "fox_history.json")
    MODS_FILE    = os.path.join(DATA_DIR, "fox_mods.json")
    ALIAS_FILE   = os.path.join(DATA_DIR, "fox_alias.json")
    ENV_FILE     = os.path.join(DATA_DIR, "fox_env.json")
    SESSION_FILE = os.path.join(DATA_DIR, "fox_session.json")

    # Correção para Android 15: Evita crash se não houver permissão de pasta externa
    if platform == "android":
        try:
            # Tenta usar a pasta FoxTerminal na memória interna visível
            from android.storage import primary_external_storage_path
            base = primary_external_storage_path()
            if base:
                EXPORT_DIR = os.path.join(base, "FoxTerminal", "exports")
            else:
                EXPORT_DIR = os.path.join(DATA_DIR, "exports")
        except Exception:
            EXPORT_DIR = os.path.join(DATA_DIR, "exports")
    else:
        EXPORT_DIR = os.path.join(DATA_DIR, "exports")
    
    try:
        os.makedirs(EXPORT_DIR, exist_ok=True)
    except Exception:
        # Se falhar (comum no Android 15 sem MANAGE_EXTERNAL_STORAGE), usa a pasta do app
        EXPORT_DIR = os.path.join(DATA_DIR, "exports")
        os.makedirs(EXPORT_DIR, exist_ok=True)
      
# ─── JSON helpers ─────────────────────────────────────────────────────────────
def _load_json(path, default):
    if not path:
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, data):
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def load_history():  return _load_json(HISTORY_FILE, [])
def save_history(h): _save_json(HISTORY_FILE, h[-200:])
def load_mods():     return _load_json(MODS_FILE, [])
def load_aliases():  return _load_json(ALIAS_FILE, {})
def save_aliases(a): _save_json(ALIAS_FILE, a)
def load_env():      return _load_json(ENV_FILE, {})
def save_env(e):     _save_json(ENV_FILE, e)

def save_mod(mod):
    mods = load_mods()
    mods = [m for m in mods if m.get("name") != mod.get("name")]
    mods.append(mod)
    _save_json(MODS_FILE, mods)

# ─── Firebase Auth (REST, sem firebase-admin) ─────────────────────────────────
class FirebaseAuth:
    """Autenticacao via Firebase Identity Toolkit REST API.
    Nao usa firebase-admin (incompativel com aarch64/Android).
    """
    def __init__(self):
        self.user      = None   # dict com localId, email, idToken, refreshToken
        self.logged_in = False
        self._load_session()

    def _load_session(self):
        data = _load_json(SESSION_FILE, {})
        if data.get("idToken") and data.get("email"):
            self.user      = data
            self.logged_in = True

    def _save_session(self):
        _save_json(SESSION_FILE, self.user or {})

    def _post(self, endpoint, payload):
        """POST para Firebase REST sem depender de requests na importacao inicial."""
        try:
            import urllib.request
            import urllib.error
            url  = f"{FIREBASE_BASE}:{endpoint}?key={FIREBASE_API_KEY}"
            body = json.dumps(payload).encode("utf-8")
            req  = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode()), None
        except Exception as e:
            # Tenta extrair mensagem do Firebase
            msg = str(e)
            try:
                import urllib.error
                if hasattr(e, "read"):
                    err_body = json.loads(e.read().decode())
                    msg = err_body.get("error", {}).get("message", msg)
            except Exception:
                pass
            return None, msg

    def register(self, email, password, callback):
        """Cria conta. callback(ok: bool, msg: str)"""
        def _run():
            data, err = self._post("signUp", {
                "email": email, "password": password, "returnSecureToken": True
            })
            if data:
                self.user      = data
                self.logged_in = True
                self._save_session()
                Clock.schedule_once(lambda dt: callback(True, "Conta criada!"))
            else:
                Clock.schedule_once(lambda dt: callback(False, err or "Erro desconhecido"))
        threading.Thread(target=_run, daemon=True).start()

    def login(self, email, password, callback):
        """Login com email/senha. callback(ok: bool, msg: str)"""
        def _run():
            data, err = self._post("signInWithPassword", {
                "email": email, "password": password, "returnSecureToken": True
            })
            if data:
                self.user      = data
                self.logged_in = True
                self._save_session()
                Clock.schedule_once(lambda dt: callback(True, "Login realizado!"))
            else:
                Clock.schedule_once(lambda dt: callback(False, err or "Email ou senha invalidos"))
        threading.Thread(target=_run, daemon=True).start()

    def logout(self):
        self.user      = None
        self.logged_in = False
        _save_json(SESSION_FILE, {})

    def reset_password(self, email, callback):
        def _run():
            data, err = self._post("sendOobCode", {
                "requestType": "PASSWORD_RESET", "email": email
            })
            if data:
                Clock.schedule_once(lambda dt: callback(True, "Email de recuperacao enviado!"))
            else:
                Clock.schedule_once(lambda dt: callback(False, err or "Erro"))
        threading.Thread(target=_run, daemon=True).start()

    @property
    def email(self):
        return (self.user or {}).get("email", "")

    @property
    def uid(self):
        return (self.user or {}).get("localId", "")


# ─── Helpers visuais ─────────────────────────────────────────────────────────
COR_FUNDO       = (0.08, 0.08, 0.10, 1)
COR_FUNDO_INPUT = (0.12, 0.12, 0.15, 1)
COR_TEXTO       = (0.85, 0.90, 0.85, 1)
COR_PROMPT      = (0.45, 0.80, 0.55, 1)
COR_ERRO        = (0.85, 0.45, 0.45, 1)
COR_BARRA       = (0.10, 0.10, 0.14, 1)
COR_LARANJA     = (0.86, 0.37, 0.14, 1)

def show_toast(label, msg, duration=3.0):
    label.text = msg
    Clock.schedule_once(lambda dt: setattr(label, 'text', ''), duration)

def colored_box(color, **kw):
    box = BoxLayout(**kw)
    with box.canvas.before:
        Color(*color)
        rect = Rectangle(size=box.size, pos=box.pos)
    box.bind(size=lambda w, v: setattr(rect, 'size', v),
             pos=lambda w, v: setattr(rect, 'pos', v))
    return box

def input_field(hint="", default="", multiline=False, height="44dp", password=False):
    return TextInput(
        text=default, hint_text=hint,
        multiline=multiline, password=password,
        size_hint_y=None, height=height,
        background_color=COR_FUNDO_INPUT,
        foreground_color=COR_TEXTO,
        cursor_color=COR_PROMPT,
        hint_text_color=(0.38, 0.38, 0.38, 1),
        font_size="14sp",
    )

# ─── TerminalOutput (sem CodeInput, sem Select All bug) ───────────────────────
class TerminalOutput(ScrollView):
    def __init__(self, initial_text="", **kw):
        super().__init__(**kw)
        self._lbl = TextInput(
            text=initial_text, readonly=True, multiline=True,
            background_color=COR_FUNDO, foreground_color=COR_TEXTO,
            font_size="13sp", size_hint_y=None,
        )
        self._lbl.bind(minimum_height=self._lbl.setter('height'))
        self._lbl.bind(text=lambda *a: Clock.schedule_once(
            lambda dt: setattr(self, 'scroll_y', 0), 0.05
        ))
        self.add_widget(self._lbl)

    @property
    def text(self): return self._lbl.text

    @text.setter
    def text(self, v): self._lbl.text = v

    def append(self, v): self._lbl.text += v


# ─── Catalogo de versoes ──────────────────────────────────────────────────────
CATALOGO = {
    "Python": [
        ("3.8.18",  "pkg install python"),
        ("3.9.18",  "pkg install python"),
        ("3.10.13", "pkg install python"),
        ("3.11.8",  "pkg install python"),
        ("3.12.2",  "pkg install python"),
        ("3.13.2",  "ja instalado no Pydroid 3"),
    ],
    "Node.js": [
        ("14.21.3", "pkg install nodejs-lts"),
        ("16.20.2", "pkg install nodejs-lts"),
        ("18.19.1", "pkg install nodejs-lts"),
        ("20.11.1", "pkg install nodejs"),
        ("21.6.2",  "pkg install nodejs"),
        ("22.0.0",  "nvm install 22"),
    ],
    "Git": [
        ("2.30.0", "pkg install git"),
        ("2.35.0", "pkg install git"),
        ("2.40.1", "pkg install git"),
        ("2.43.0", "pkg install git"),
        ("2.44.0", "apt install git"),
    ],
    "pip": [
        ("22.0", "python -m pip install --upgrade pip"),
        ("23.0", "python -m pip install --upgrade pip"),
        ("23.3", "python -m pip install --upgrade pip"),
        ("24.0", "python -m pip install --upgrade pip"),
    ],
    "npm": [
        ("8.19.4", "npm install -g npm@8"),
        ("9.9.3",  "npm install -g npm@9"),
        ("10.5.0", "npm install -g npm@10"),
    ],
    "Kivy": [
        ("2.1.0", "pip install kivy==2.1.0"),
        ("2.2.1", "pip install kivy==2.2.1"),
        ("2.3.1", "pip install kivy==2.3.1"),
    ],
    "KivyMD": [
        ("1.1.1", "pip install kivymd==1.1.1"),
        ("1.2.0", "pip install kivymd==1.2.0"),
        ("2.0.0", "pip install https://github.com/kivymd/KivyMD/archive/master.zip"),
    ],
    "Termux": [
        ("pkg",     "apt update && apt upgrade"),
        ("clang",   "pkg install clang"),
        ("cmake",   "pkg install cmake"),
        ("curl",    "pkg install curl"),
        ("wget",    "pkg install wget"),
        ("openssh", "pkg install openssh"),
        ("vim",     "pkg install vim"),
        ("nano",    "pkg install nano"),
        ("ffmpeg",  "pkg install ffmpeg"),
    ],
    "Ruby":        [("3.1.4","pkg install ruby"),("3.2.3","pkg install ruby"),("3.3.0","pkg install ruby")],
    "Lua":         [("5.3.6","pkg install lua53"),("5.4.6","pkg install lua54")],
    "Rust":        [("1.75.0","pkg install rust"),("1.77.0","curl https://sh.rustup.rs -sSf | sh")],
    "Go":          [("1.21.0","pkg install golang"),("1.22.0","pkg install golang")],
    "Java":        [("11","pkg install openjdk-11"),("17","pkg install openjdk-17"),("21","pkg install openjdk-21")],
    "SQLite":      [("3.40.0","pkg install sqlite"),("3.45.0","pkg install sqlite")],
}

AJUDA = f"""Fox Terminal {VERSION}
-----------------------------
  clear/cls      Limpa tela
  cd <pasta>     Muda diretorio
  pwd            Diretorio atual
  ls             Lista arquivos
  cat <arq>      Ver arquivo
  mkdir <pasta>  Criar pasta
  rm <arq>       Remover
  cp <o> <d>     Copiar
  mv <o> <d>     Mover/renomear
  echo <txt>     Imprimir texto
  env            Variaveis de ambiente
  set VAR=val    Definir variavel
  unset VAR      Remover variavel
  alias          Listar aliases
  alias n=cmd    Definir alias
  unalias n      Remover alias
  history        Historico
  help           Esta ajuda
  exit/quit      Fechar app
-----------------------------
Outros comandos vao para o SO.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SPLASH SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class SplashScreen(MDScreen):
    """Tela de carregamento exibida enquanto o app inicializa."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "splash"

        root = FloatLayout()

        # Fundo preto total
        with root.canvas.before:
            Color(0.06, 0.06, 0.08, 1)
            self._bg = Rectangle(size=root.size, pos=root.pos)
        root.bind(size=lambda w, v: setattr(self._bg, 'size', v),
                  pos=lambda w, v: setattr(self._bg, 'pos', v))

        center = BoxLayout(
            orientation='vertical', spacing=dp(16),
            size_hint=(None, None), size=(dp(260), dp(220)),
            pos_hint={"center_x": .5, "center_y": .55}
        )

        # Logo: "Fx🦊" grande
        logo = MDLabel(
            text="Fox Terminal",
            font_style="H4",
            halign="center",
            theme_text_color="Custom",
            text_color=COR_PROMPT,
        )
        center.add_widget(logo)

        sub = MDLabel(
            text=VERSION,
            font_style="Caption",
            halign="center",
            theme_text_color="Custom",
            text_color=(0.5, 0.6, 0.5, 1),
        )
        center.add_widget(sub)

        self.bar = MDProgressBar(
            value=0, size_hint_y=None, height=dp(4)
        )
        center.add_widget(self.bar)

        self.status = MDLabel(
            text="Inicializando...",
            font_style="Caption",
            halign="center",
            theme_text_color="Custom",
            text_color=(0.45, 0.5, 0.45, 1),
        )
        center.add_widget(self.status)

        root.add_widget(center)
        self.add_widget(root)

    def start(self, on_done):
        """Anima a barra e chama on_done() ao terminar."""
        steps = [
            (0.4,  "Carregando interface..."),
            (0.7,  "Preparando terminal..."),
            (0.9,  "Quase pronto..."),
            (1.0,  "Pronto!"),
        ]
        def _step(i, dt):
            if i >= len(steps):
                Clock.schedule_once(lambda dt2: on_done(), 0.2)
                return
            val, msg = steps[i]
            self.bar.value   = val * 100
            self.status.text = msg
            Clock.schedule_once(lambda dt2, ni=i+1: _step(ni, dt2), 0.45)

        Clock.schedule_once(lambda dt: _step(0, dt), 0.1)


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN / REGISTRO / RECUPERAR SENHA
# ══════════════════════════════════════════════════════════════════════════════
class AuthScreen(MDScreen):
    """Tela unificada de login, registro e recuperar senha."""
    def __init__(self, auth: FirebaseAuth, **kw):
        super().__init__(**kw)
        self.name = "auth"
        self.auth = auth
        self._mode = "login"   # "login" | "register" | "reset"

        root = ScrollView()
        layout = BoxLayout(
            orientation='vertical', padding=dp(24), spacing=dp(10),
            size_hint_y=None
        )
        layout.bind(minimum_height=layout.setter('height'))

        # Cabecalho
        self.title_lbl = MDLabel(
            text="Entrar",
            font_style="H5", halign="center",
            theme_text_color="Custom", text_color=COR_PROMPT,
            size_hint_y=None, height=dp(52),
        )
        layout.add_widget(self.title_lbl)

        self.subtitle = MDLabel(
            text="Faca login para sincronizar seus terminais.",
            font_style="Caption", halign="center",
            theme_text_color="Custom", text_color=(0.55,0.6,0.55,1),
            size_hint_y=None, height=dp(32),
        )
        layout.add_widget(self.subtitle)

        # Campos
        layout.add_widget(MDLabel(text="E-mail", size_hint_y=None, height=dp(24),
                                  theme_text_color="Secondary"))
        self.f_email = input_field("seu@email.com")
        layout.add_widget(self.f_email)

        self.lbl_pass = MDLabel(text="Senha", size_hint_y=None, height=dp(24),
                                theme_text_color="Secondary")
        layout.add_widget(self.lbl_pass)
        self.f_pass = input_field("Minimo 6 caracteres", password=True)
        layout.add_widget(self.f_pass)

        self.lbl_pass2 = MDLabel(text="Confirmar Senha", size_hint_y=None, height=dp(24),
                                 theme_text_color="Secondary")
        self.f_pass2 = input_field("Repita a senha", password=True)
        # Escondido no login
        self.lbl_pass2.opacity  = 0
        self.lbl_pass2.size_hint_y = None
        self.lbl_pass2.height   = 0
        self.f_pass2.opacity    = 0
        self.f_pass2.size_hint_y = None
        self.f_pass2.height     = 0
        layout.add_widget(self.lbl_pass2)
        layout.add_widget(self.f_pass2)

        # Feedback
        self.msg = MDLabel(
            text="", halign="center",
            size_hint_y=None, height=dp(36),
            theme_text_color="Secondary", font_style="Caption"
        )
        layout.add_widget(self.msg)

        # Botao principal
        self.btn_main = MDRaisedButton(
            text="Entrar",
            pos_hint={"center_x": .5},
            size_hint_y=None, height=dp(48),
            on_release=self._on_main
        )
        layout.add_widget(self.btn_main)

        # Links secundarios
        links = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        self.btn_toggle = MDRaisedButton(
            text="Criar conta",
            size_hint_y=None, height=dp(36),
            on_release=self._toggle_mode
        )
        self.btn_reset = MDRaisedButton(
            text="Esqueci a senha",
            size_hint_y=None, height=dp(36),
            on_release=self._go_reset
        )
        links.add_widget(self.btn_toggle)
        links.add_widget(self.btn_reset)
        layout.add_widget(links)

        # Pular login
        layout.add_widget(MDRaisedButton(
            text="Usar sem conta (offline)",
            pos_hint={"center_x": .5},
            size_hint_y=None, height=dp(40),
            on_release=lambda x: MDApp.get_running_app().go_main()
        ))

        root.add_widget(layout)
        self.add_widget(root)

    def _toggle_mode(self, *a):
        if self._mode == "login":
            self._mode = "register"
            self.title_lbl.text   = "Criar Conta"
            self.subtitle.text    = "Seus dados ficarao sincronizados."
            self.btn_main.text    = "Registrar"
            self.btn_toggle.text  = "Ja tenho conta"
            self._show_confirm(True)
        elif self._mode == "register":
            self._mode = "login"
            self.title_lbl.text   = "Entrar"
            self.subtitle.text    = "Faca login para sincronizar seus terminais."
            self.btn_main.text    = "Entrar"
            self.btn_toggle.text  = "Criar conta"
            self._show_confirm(False)
        else:
            self._mode = "login"
            self.title_lbl.text   = "Entrar"
            self.btn_main.text    = "Entrar"
            self.btn_toggle.text  = "Criar conta"
            self.lbl_pass.opacity = 1
            self.lbl_pass.height  = dp(24)
            self.f_pass.opacity   = 1
            self.f_pass.height    = dp(44)
            self._show_confirm(False)

    def _go_reset(self, *a):
        self._mode            = "reset"
        self.title_lbl.text   = "Recuperar Senha"
        self.subtitle.text    = "Enviaremos um email de recuperacao."
        self.btn_main.text    = "Enviar email"
        self.lbl_pass.opacity = 0
        self.lbl_pass.height  = 0
        self.f_pass.opacity   = 0
        self.f_pass.height    = 0
        self._show_confirm(False)

    def _show_confirm(self, show):
        h = dp(44) if show else 0
        h2 = dp(24) if show else 0
        op = 1 if show else 0
        self.lbl_pass2.opacity    = op
        self.lbl_pass2.height     = h2
        self.f_pass2.opacity      = op
        self.f_pass2.height       = h

    def _on_main(self, *a):
        email = self.f_email.text.strip()
        pwd   = self.f_pass.text.strip()
        if not email:
            show_toast(self.msg, "Informe o e-mail.")
            return

        self.btn_main.disabled = True
        show_toast(self.msg, "Aguarde...", duration=10)

        def _cb(ok, msg):
            self.btn_main.disabled = False
            show_toast(self.msg, msg)
            if ok:
                Clock.schedule_once(
                    lambda dt: MDApp.get_running_app().go_main(), 1.2
                )

        if self._mode == "login":
            if not pwd:
                show_toast(self.msg, "Informe a senha.")
                self.btn_main.disabled = False
                return
            self.auth.login(email, pwd, _cb)

        elif self._mode == "register":
            pwd2 = self.f_pass2.text.strip()
            if len(pwd) < 6:
                show_toast(self.msg, "Senha deve ter ao menos 6 caracteres.")
                self.btn_main.disabled = False
                return
            if pwd != pwd2:
                show_toast(self.msg, "Senhas nao coincidem.")
                self.btn_main.disabled = False
                return
            self.auth.register(email, pwd, _cb)

        elif self._mode == "reset":
            self.auth.reset_password(email, _cb)


# ══════════════════════════════════════════════════════════════════════════════
# TERMINAL
# ══════════════════════════════════════════════════════════════════════════════
class TerminalScreen(MDScreen):
    def __init__(self, page_num, **kw):
        super().__init__(**kw)
        self.name          = f"page_{page_num}"
        self.page_num      = page_num
        self.cwd           = os.path.expanduser("~")
        self.cmd_history   = load_history()
        self.history_index = len(self.cmd_history)
        self.process       = None
        self.aliases       = load_aliases()
        self.env_vars      = load_env()

        layout = BoxLayout(orientation='vertical')

        self.progress = MDProgressBar(value=0, size_hint_y=None, height=dp(3), opacity=0)

        self.output = TerminalOutput(
            initial_text=(
                f"Fox Terminal {VERSION}\n"
                f"Terminal {page_num}  |  {self.cwd}\n"
                f"Digite 'help' para ajuda.\n$ "
            )
        )

        input_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(2))
        self.input = TextInput(
            multiline=False,
            background_color=COR_FUNDO_INPUT, foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT, hint_text="Comando...",
            hint_text_color=(0.38,0.38,0.38,1), font_size="14sp",
        )
        self.input.bind(on_text_validate=self.process_command)

        for icon, cb in [
            ("arrow-up",    lambda x: self.nav_history(-1)),
            ("arrow-down",  lambda x: self.nav_history(1)),
            ("stop-circle", self.stop_process),
            ("broom",       self.clear_output),
        ]:
            kw2 = dict(icon=icon, size_hint_x=None, width=dp(44), on_release=cb)
            if icon == "stop-circle":
                kw2.update(theme_text_color="Custom", text_color=COR_ERRO)
            input_row.add_widget(MDIconButton(**kw2))

        input_row.children[-1]  # reorder: input first
        input_row.clear_widgets()
        input_row.add_widget(self.input)
        for icon, cb in [
            ("arrow-up",    lambda x: self.nav_history(-1)),
            ("arrow-down",  lambda x: self.nav_history(1)),
            ("stop-circle", self.stop_process),
            ("broom",       self.clear_output),
        ]:
            kw2 = dict(icon=icon, size_hint_x=None, width=dp(44), on_release=cb)
            if icon == "stop-circle":
                kw2.update(theme_text_color="Custom", text_color=COR_ERRO)
            input_row.add_widget(MDIconButton(**kw2))

        layout.add_widget(self.progress)
        layout.add_widget(self.output)
        layout.add_widget(input_row)
        self.add_widget(layout)

    def nav_history(self, direction):
        if not self.cmd_history: return
        self.history_index = max(0, min(len(self.cmd_history)-1, self.history_index+direction))
        self.input.text = self.cmd_history[self.history_index]

    def write(self, txt): self.output.append(txt)

    def process_command(self, instance):
        raw = self.input.text.strip()
        self.input.text = ""
        if not raw: return

        # Alias
        parts = raw.split(None, 1)
        if parts[0] in self.aliases:
            raw = self.aliases[parts[0]] + ("" if len(parts)==1 else " "+parts[1])

        # Env vars
        for k, v in self.env_vars.items():
            raw = raw.replace(f"${k}", v)

        if not self.cmd_history or self.cmd_history[-1] != raw:
            self.cmd_history.append(raw)
            save_history(self.cmd_history)
        self.history_index = len(self.cmd_history)

        self.write(f"$ {raw}\n")
        self._handle(raw)

    def _abs(self, p):
        return os.path.normpath(
            os.path.join(self.cwd, p) if not os.path.isabs(p) else p
        )

    def _handle(self, cmd):
        p = cmd.split()
        b = p[0] if p else ""

        if cmd in ("clear","cls"):
            self.clear_output(None); return
        elif cmd in ("help","--help"):
            self.write(AJUDA)
        elif cmd == "pwd":
            self.write(self.cwd+"\n")
        elif b == "cd":
            path = cmd[2:].strip() or os.path.expanduser("~")
            new  = self._abs(path)
            if os.path.isdir(new): self.cwd = new; self.write(f"-> {new}\n")
            else: self.write(f"cd: '{path}': nao encontrado\n")
        elif b == "ls":
            self._ls(p[1] if len(p)>1 else ".")
        elif b == "cat":
            self._cat(p[1]) if len(p)>1 else self.write("[erro] uso: cat <arq>\n")
        elif b == "mkdir":
            self._mkdir(p[1]) if len(p)>1 else self.write("[erro] uso: mkdir <pasta>\n")
        elif b == "rm":
            self._rm(p[1]) if len(p)>1 else self.write("[erro] uso: rm <arq>\n")
        elif b == "cp":
            self._cp(p[1],p[2]) if len(p)>2 else self.write("[erro] uso: cp <o> <d>\n")
        elif b == "mv":
            self._mv(p[1],p[2]) if len(p)>2 else self.write("[erro] uso: mv <o> <d>\n")
        elif b == "echo":
            self.write(" ".join(p[1:])+"\n")
        elif cmd == "env":
            [self.write(f"  {k}={v}\n") for k,v in self.env_vars.items()] \
                or self.write("Nenhuma variavel.\n")
        elif b == "set" and "=" in cmd:
            k,_,v = cmd[4:].strip().partition("=")
            self.env_vars[k.strip()] = v.strip(); save_env(self.env_vars)
            self.write(f"  {k.strip()} = {v.strip()}\n")
        elif b == "unset" and len(p)>1:
            self.env_vars.pop(p[1],None); save_env(self.env_vars)
            self.write(f"  {p[1]} removida.\n")
        elif b == "alias" and "=" in cmd:
            k,_,v = cmd[5:].strip().partition("=")
            self.aliases[k.strip()] = v.strip(); save_aliases(self.aliases)
            self.write(f"  alias {k.strip()} = '{v.strip()}'\n")
        elif cmd == "alias":
            [self.write(f"  {k}='{v}'\n") for k,v in self.aliases.items()] \
                or self.write("Nenhum alias.\n")
        elif b == "unalias" and len(p)>1:
            self.aliases.pop(p[1],None); save_aliases(self.aliases)
            self.write(f"  alias '{p[1]}' removido.\n")
        elif cmd == "history":
            [self.write(f"  {i:>3}  {h}\n") for i,h in enumerate(self.cmd_history[-30:],1)]
        elif cmd in ("exit","quit"):
            MDApp.get_running_app().stop(); return
        else:
            self.progress.opacity = 1
            env = os.environ.copy()
            env.update(self.env_vars)
            if platform == "android" and DATA_DIR:
                sp = os.path.join(DATA_DIR, "site-packages")
                os.makedirs(sp, exist_ok=True)
                env["PYTHONPATH"]  = sp + os.pathsep + env.get("PYTHONPATH","")
                env["PIP_TARGET"]  = sp
                env["HOME"]        = DATA_DIR
            threading.Thread(target=self.run_sys, args=(cmd,env), daemon=True).start()
            return
        self.write("$ ")

    def _ls(self, path):
        try:
            items = sorted(os.listdir(self._abs(path)))
            for i in items:
                t = "[D]" if os.path.isdir(os.path.join(self._abs(path),i)) else "[F]"
                self.write(f"  {t} {i}\n")
            if not items: self.write("(vazio)\n")
        except Exception as e: self.write(f"[erro] {e}\n")

    def _cat(self, f):
        try:
            with open(self._abs(f),"r",errors="replace") as fh: c=fh.read()
            self.write(c if c.endswith("\n") else c+"\n")
        except Exception as e: self.write(f"[erro] {e}\n")

    def _mkdir(self, n):
        try: os.makedirs(self._abs(n),exist_ok=True); self.write(f"Criado: {self._abs(n)}\n")
        except Exception as e: self.write(f"[erro] {e}\n")

    def _rm(self, n):
        p=self._abs(n)
        try:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            self.write(f"Removido: {p}\n")
        except Exception as e: self.write(f"[erro] {e}\n")

    def _cp(self,s,d):
        try: shutil.copy2(self._abs(s),self._abs(d)); self.write(f"Copiado.\n")
        except Exception as e: self.write(f"[erro] {e}\n")

    def _mv(self,s,d):
        try: shutil.move(self._abs(s),self._abs(d)); self.write(f"Movido.\n")
        except Exception as e: self.write(f"[erro] {e}\n")

    def run_sys(self, cmd, env):
        _out = _err = ""
        _code = 1
        try:
            self.process = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=self.cwd, env=env
            )
            _out, _err = self.process.communicate(timeout=120)
            _code = self.process.returncode if self.process is not None else 1
        except subprocess.TimeoutExpired:
            if self.process is not None:
                try: self.process.kill(); self.process.communicate()
                except Exception: pass
            _err  = "Tempo limite (120s) excedido\n"
            _code = 1
        except Exception as e:
            _err  = str(e)+"\n"
            _code = 1
        finally:
            self.process = None
        Clock.schedule_once(lambda dt: self.done(_out, _err, _code))

    def done(self, out, err, code):
        if out: self.write(out)
        if err: self.write(f"[erro] {err}\n")
        self.write(f"{'[ok]' if code==0 else f'[falhou:{code}]'}\n$ ")
        self.progress.opacity = 0

    def stop_process(self, instance):
        if self.process:
            try: self.process.kill(); self.write("\n[encerrado]\n$ ")
            except Exception: pass
        else: self.write("[sem processo]\n$ ")

    def clear_output(self, instance):
        self.output.text = f"Fox Terminal {VERSION}  |  Terminal {self.page_num}\n$ "


# ══════════════════════════════════════════════════════════════════════════════
# VERSOES E PACOTES
# ══════════════════════════════════════════════════════════════════════════════
class VersionManagerScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.all_items = [(p,v,c) for p,es in CATALOGO.items() for v,c in es]

        layout = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        layout.add_widget(MDLabel(
            text="Versoes e Pacotes", font_style="H6", halign="center",
            size_hint_y=None, height=dp(44)
        ))

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.search = TextInput(
            hint_text="Pesquisar pacote ou versao...",
            hint_text_color=(0.38,0.38,0.38,1), multiline=False,
            background_color=COR_FUNDO_INPUT, foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT, font_size="14sp",
        )
        self.search.bind(text=self._on_search)
        row.add_widget(self.search)
        row.add_widget(MDIconButton(
            icon="close-circle", size_hint_x=None, width=dp(44),
            on_release=lambda x: setattr(self.search,'text','')
        ))
        layout.add_widget(row)

        self.count = MDLabel(
            text=f"{len(self.all_items)} pacotes",
            font_style="Caption", halign="center",
            size_hint_y=None, height=dp(22), theme_text_color="Secondary"
        )
        layout.add_widget(self.count)

        self.scroll = ScrollView()
        self.pkg_list = MDList()
        self.scroll.add_widget(self.pkg_list)
        layout.add_widget(self.scroll)

        # Detalhe sem TextInput (sem selecao azul)
        dbox = colored_box(COR_FUNDO_INPUT, size_hint_y=None, height=dp(72), padding=dp(8))
        self.detail = MDLabel(
            text="Toque em um item para ver o comando.",
            font_style="Caption", theme_text_color="Custom",
            text_color=COR_PROMPT, halign="left", valign="middle",
        )
        dbox.add_widget(self.detail)
        layout.add_widget(dbox)

        layout.add_widget(MDRaisedButton(
            text="Voltar", pos_hint={"center_x":.5},
            size_hint_y=None, height=dp(44),
            on_release=lambda x: MDApp.get_running_app().set_screen("page_1")
        ))
        self.add_widget(layout)
        self._populate(self.all_items)

    def _populate(self, items):
        self.pkg_list.clear_widgets()
        if not items:
            self.pkg_list.add_widget(MDLabel(
                text="Nenhum resultado.", halign="center",
                size_hint_y=None, height=dp(48), theme_text_color="Secondary"
            ))
        else:
            for p,v,c in items:
                it = OneLineIconListItem(
                    text=f"{p}   {v}",
                    on_release=lambda x,pp=p,vv=v,cc=c: setattr(
                        self.detail,'text',f"{pp} {vv}\nInstalar: {cc}"
                    )
                )
                it.add_widget(IconLeftWidget(icon="package-variant"))
                self.pkg_list.add_widget(it)
        self.count.text = f"{len(items)} resultado(s)"

    def _on_search(self, inst, val):
        q = val.strip().lower()
        self._populate(self.all_items if not q else [
            (p,v,c) for p,v,c in self.all_items
            if q in p.lower() or q in v.lower() or q in c.lower()
        ])


# ══════════════════════════════════════════════════════════════════════════════
# LOJA DE MODS
# ══════════════════════════════════════════════════════════════════════════════
class StoreScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(8))
        layout.add_widget(MDLabel(
            text="Loja de Mods", font_style="H5", halign="center",
            size_hint_y=None, height=dp(48)
        ))
        self.msg = MDLabel(text="", halign="center", size_hint_y=None, height=dp(28),
                           theme_text_color="Secondary")
        layout.add_widget(self.msg)

        scroll = ScrollView()
        lst = MDList()
        mods = [
            ("language-python",     "Python Editor  -  editor e console Python",     "python_editor"),
            ("language-javascript", "Node.js REPL  -  execute JavaScript",            "node_repl"),
            ("git",                 "Git Helper  -  atalhos para Git",                "git_helper"),
            ("file-code",           "Editor de Arquivos  -  abrir e editar arquivos", "file_editor"),
        ]
        for icon, title, screen in mods:
            it = OneLineIconListItem(
                text=title,
                on_release=lambda x,s=screen,t=title: self._activate(s,t)
            )
            it.add_widget(IconLeftWidget(icon=icon))
            lst.add_widget(it)
        scroll.add_widget(lst)
        layout.add_widget(scroll)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(MDRaisedButton(
            text="Exportar Mods",
            on_release=lambda x: MDApp.get_running_app().set_screen("export")
        ))
        row.add_widget(MDRaisedButton(
            text="Voltar",
            on_release=lambda x: MDApp.get_running_app().set_screen("page_1")
        ))
        layout.add_widget(row)
        self.add_widget(layout)

    def _activate(self, screen, title):
        app = MDApp.get_running_app()
        app.activate_mod(screen)
        show_toast(self.msg, f"Mod ativado: {title.split('-')[0].strip()}")


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTAR MODS
# ══════════════════════════════════════════════════════════════════════════════
class ExportScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        outer = ScrollView()
        layout = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(10),
                           size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        layout.add_widget(MDLabel(
            text="Exportar Mod", font_style="H5", halign="center",
            size_hint_y=None, height=dp(48)
        ))

        for lbl, attr, hint, default in [
            ("Nome (sem espacos):", "f_name",    "meu_mod",     "meu_mod"),
            ("Versao:",             "f_version", "1.0.0",       "1.0.0"),
            ("Autor (GitHub):",     "f_author",  "seu_usuario", ""),
        ]:
            layout.add_widget(MDLabel(text=lbl, size_hint_y=None, height=dp(26),
                                      theme_text_color="Secondary"))
            f = input_field(hint, default)
            setattr(self, attr, f)
            layout.add_widget(f)

        layout.add_widget(MDLabel(text="Descricao:", size_hint_y=None, height=dp(26),
                                  theme_text_color="Secondary"))
        self.f_desc = input_field("O que este mod faz?", multiline=True, height="72dp")
        layout.add_widget(self.f_desc)

        self.result = MDLabel(text="", halign="center", size_hint_y=None, height=dp(40),
                              theme_text_color="Secondary", font_style="Caption")
        layout.add_widget(self.result)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        row.add_widget(MDRaisedButton(text="Gerar .zip",         on_release=self._export))
        row.add_widget(MDRaisedButton(text="Instrucoes GitHub",  on_release=self._show_github))
        row.add_widget(MDRaisedButton(text="Voltar",             on_release=lambda x: MDApp.get_running_app().set_screen("store")))
        layout.add_widget(row)

        # Instrucoes — MDLabel sem selecao
        iscroll = ScrollView(size_hint_y=None, height=dp(300))
        ibox = colored_box(COR_FUNDO, size_hint_y=None, padding=dp(8))
        self.instructions = MDLabel(
            text="", font_style="Caption",
            theme_text_color="Custom", text_color=COR_TEXTO,
            halign="left", valign="top", size_hint_y=None,
        )
        self.instructions.bind(
            texture_size=lambda w,v: setattr(w,'height',max(v[1],dp(300)))
        )
        ibox.bind(minimum_height=ibox.setter('height'))
        ibox.add_widget(self.instructions)
        iscroll.add_widget(ibox)
        layout.add_widget(iscroll)

        outer.add_widget(layout)
        self.add_widget(outer)

    def _export(self, *a):
        name    = self.f_name.text.strip().replace(" ","_") or "meu_mod"
        version = self.f_version.text.strip() or "1.0.0"
        author  = self.f_author.text.strip() or "desconhecido"
        desc    = self.f_desc.text.strip() or "Mod Fox Terminal"
        show_toast(self.result, "Gerando .zip...")
        threading.Thread(target=self._do, args=(name,version,author,desc), daemon=True).start()

    def _do(self, name, version, author, desc):
        try:
            mod_dir  = os.path.join(EXPORT_DIR, name)
            zip_path = os.path.join(EXPORT_DIR, f"{name}-{version}.zip")
            os.makedirs(mod_dir, exist_ok=True)
            _save_json(os.path.join(mod_dir,"mod.json"),
                       {"name":name,"version":version,"author":author,
                        "description":desc,"fox_version":VERSION})
            with open(os.path.join(mod_dir,"README.md"),"w") as f:
                f.write(f"# {name}\n\n**Versao:** {version}  \n**Autor:** {author}\n\n{desc}\n")
            if MODS_FILE and os.path.exists(MODS_FILE):
                shutil.copy(MODS_FILE, os.path.join(mod_dir,"fox_mods.json"))
            with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as zf:
                for fn in os.listdir(mod_dir):
                    zf.write(os.path.join(mod_dir,fn), arcname=fn)
            shutil.rmtree(mod_dir, ignore_errors=True)
            Clock.schedule_once(lambda dt: self._done(zip_path))
        except Exception as e:
            Clock.schedule_once(lambda dt: show_toast(self.result, f"Erro: {e}"))

    def _done(self, zip_path):
        show_toast(self.result, "Exportado!", duration=4)
        self.instructions.text = (
            f"Arquivo:\n{zip_path}\n\n"
            "=== GitHub ===\n\n"
            f"cd {EXPORT_DIR}\n"
            "git init\ngit add .\n"
            "git commit -m \"meu mod\"\n"
            "git branch -M main\n"
            "git remote add origin https://github.com/USUARIO/REPO.git\n"
            "git push -u origin main\n"
        )

    def _show_github(self, *a):
        self.instructions.text = (
            "=== Publicar no GitHub ===\n\n"
            "1. github.com/new  ->  criar repo\n"
            "2. Gere o .zip com o botao acima\n"
            "3. No terminal Fox:\n\n"
            f"   cd {EXPORT_DIR}\n"
            "   git init\n   git add .\n"
            "   git commit -m \"primeiro commit\"\n"
            "   git remote add origin https://github.com/USUARIO/REPO.git\n"
            "   git push -u origin main\n\n"
            "4. Releases > Draft > anexe o .zip\n"
        )


# ══════════════════════════════════════════════════════════════════════════════
# PYTHON EDITOR + CONSOLE
# ══════════════════════════════════════════════════════════════════════════════
class PythonEditorScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation='vertical')
        tb = colored_box(COR_BARRA, size_hint_y=None, height=dp(48), padding=dp(4), spacing=dp(4))
        tb.add_widget(MDLabel(text="Python Editor", font_style="Subtitle1"))
        tb.add_widget(MDIconButton(icon="play", theme_text_color="Custom",
                                   text_color=COR_PROMPT, on_release=self.run_code))
        tb.add_widget(MDIconButton(icon="delete-outline", theme_text_color="Custom",
                                   text_color=COR_ERRO, on_release=lambda x: setattr(self.code,'text','')))
        tb.add_widget(MDIconButton(icon="arrow-left",
                                   on_release=lambda x: MDApp.get_running_app().set_screen("store")))
        self.code = TextInput(
            text='# Fox Terminal - Python Editor\n\nprint("Ola!")\n',
            multiline=True, background_color=COR_FUNDO,
            foreground_color=COR_TEXTO, cursor_color=COR_PROMPT, font_size="14sp",
        )
        layout.add_widget(tb)
        layout.add_widget(self.code)
        self.add_widget(layout)

    def run_code(self, *a):
        app = MDApp.get_running_app()
        app.sm.get_screen("python_console").run_and_show(self.code.text)
        app.set_screen("python_console")


class PythonConsoleScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation='vertical')
        tb = colored_box(COR_BARRA, size_hint_y=None, height=dp(48), padding=dp(4))
        tb.add_widget(MDLabel(text="Saida Python", font_style="Subtitle1"))
        tb.add_widget(MDIconButton(icon="arrow-left",
                                   on_release=lambda x: MDApp.get_running_app().set_screen("python_editor")))
        self.out = TerminalOutput()
        layout.add_widget(tb)
        layout.add_widget(self.out)
        self.add_widget(layout)

    def run_and_show(self, code):
        old_o, old_e = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        try:
            exec(compile(code,"<fox>","exec"), {})
            r = sys.stdout.getvalue()
            self.out.text = r if r else "(sem saida)"
        except Exception:
            import traceback
            self.out.text = f"Erro:\n{traceback.format_exc()}"
        finally:
            sys.stdout, sys.stderr = old_o, old_e


# ══════════════════════════════════════════════════════════════════════════════
# NODE REPL
# ══════════════════════════════════════════════════════════════════════════════
class NodeReplScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation='vertical')
        tb = colored_box(COR_BARRA, size_hint_y=None, height=dp(48), padding=dp(4), spacing=dp(4))
        tb.add_widget(MDLabel(text="Node.js REPL", font_style="Subtitle1"))
        tb.add_widget(MDIconButton(icon="arrow-left",
                                   on_release=lambda x: MDApp.get_running_app().set_screen("store")))
        self.out = TerminalOutput("Node.js REPL\nVerificando node...\n")
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        self.inp = TextInput(multiline=False, background_color=COR_FUNDO_INPUT,
                             foreground_color=COR_TEXTO, cursor_color=COR_PROMPT,
                             hint_text="Expressao JS...", hint_text_color=(0.38,0.38,0.38,1),
                             font_size="14sp")
        self.inp.bind(on_text_validate=self.run_js)
        row.add_widget(self.inp)
        row.add_widget(MDIconButton(icon="play", theme_text_color="Custom",
                                    text_color=COR_PROMPT, on_release=self.run_js))
        layout.add_widget(tb); layout.add_widget(self.out); layout.add_widget(row)
        self.add_widget(layout)
        Clock.schedule_once(lambda dt: threading.Thread(target=self._check, daemon=True).start(), 0.5)

    def _check(self):
        try:
            r = subprocess.run(["node","--version"], capture_output=True, text=True, timeout=5)
            v = r.stdout.strip()
            Clock.schedule_once(lambda dt: setattr(self.out,'text',f"Node.js {v}\n> "))
        except Exception:
            Clock.schedule_once(lambda dt: setattr(self.out,'text',
                "Node.js nao encontrado.\npkg install nodejs\n"))

    def run_js(self, *a):
        code = self.inp.text.strip(); self.inp.text = ""
        if not code: return
        self.out.append(f"> {code}\n")
        threading.Thread(target=self._exec, args=(code,), daemon=True).start()

    def _exec(self, code):
        try:
            r = subprocess.run(
                ["node","-e",f"try{{console.log(eval({json.dumps(code)}))}}catch(e){{console.error(e.message)}}"],
                capture_output=True, text=True, timeout=10)
            out = (r.stdout or r.stderr or "(sem saida)").strip()
            Clock.schedule_once(lambda dt: self.out.append(f"{out}\n> "))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.out.append(f"[erro] {e}\n"))


# ══════════════════════════════════════════════════════════════════════════════
# GIT HELPER
# ══════════════════════════════════════════════════════════════════════════════
class GitHelperScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation='vertical')
        tb = colored_box(COR_BARRA, size_hint_y=None, height=dp(48), padding=dp(4), spacing=dp(4))
        tb.add_widget(MDLabel(text="Git Helper", font_style="Subtitle1"))
        tb.add_widget(MDIconButton(icon="arrow-left",
                                   on_release=lambda x: MDApp.get_running_app().set_screen("store")))
        self.out = TerminalOutput("Git Helper\n")

        scroll = ScrollView(size_hint_y=None, height=dp(200))
        lst = MDList()
        for icon, cmd, desc in [
            ("git",          "git status",               "Status"),
            ("source-branch","git log --oneline -10",    "Ultimos 10 commits"),
            ("plus",         "git add .",                "Adicionar tudo"),
            ("check",        "git commit -m 'update'",   "Commit rapido"),
            ("upload",       "git push",                 "Push"),
            ("download",     "git pull",                 "Pull"),
            ("source-fork",  "git clone",                "Clone"),
            ("delete",       "git stash",                "Stash"),
            ("history",      "git diff",                 "Diff"),
        ]:
            it = OneLineIconListItem(text=desc, on_release=lambda x,c=cmd: self.run_git(c))
            it.add_widget(IconLeftWidget(icon=icon))
            lst.add_widget(it)
        scroll.add_widget(lst)

        pr = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4), padding=dp(4))
        self.path_inp = TextInput(hint_text="Caminho do repo (vazio = home)",
                                  hint_text_color=(0.38,0.38,0.38,1), multiline=False,
                                  background_color=COR_FUNDO_INPUT, foreground_color=COR_TEXTO,
                                  cursor_color=COR_PROMPT, font_size="12sp")
        pr.add_widget(self.path_inp)

        cr = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4), padding=dp(4))
        self.cmd_inp = TextInput(hint_text="git <comando>",
                                 hint_text_color=(0.38,0.38,0.38,1), multiline=False,
                                 background_color=COR_FUNDO_INPUT, foreground_color=COR_TEXTO,
                                 cursor_color=COR_PROMPT, font_size="13sp")
        self.cmd_inp.bind(on_text_validate=lambda x: self.run_git(self.cmd_inp.text))
        cr.add_widget(self.cmd_inp)
        cr.add_widget(MDRaisedButton(text="Executar", size_hint_x=None, width=dp(100),
                                     on_release=lambda x: self.run_git(self.cmd_inp.text)))

        layout.add_widget(tb); layout.add_widget(scroll)
        layout.add_widget(pr); layout.add_widget(cr); layout.add_widget(self.out)
        self.add_widget(layout)

    def run_git(self, cmd):
        cwd = self.path_inp.text.strip() or os.path.expanduser("~")
        self.out.append(f"\n$ {cmd}\n")
        threading.Thread(target=self._exec, args=(cmd,cwd), daemon=True).start()

    def _exec(self, cmd, cwd):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=30)
            out = r.stdout or r.stderr or "(sem saida)"
            Clock.schedule_once(lambda dt: self.out.append(out))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.out.append(f"[erro] {e}\n"))


# ══════════════════════════════════════════════════════════════════════════════
# EDITOR DE ARQUIVOS
# ══════════════════════════════════════════════════════════════════════════════
class FileEditorScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.current_file = None
        layout = BoxLayout(orientation='vertical')
        tb = colored_box(COR_BARRA, size_hint_y=None, height=dp(48), padding=dp(4), spacing=dp(4))
        self.file_lbl = MDLabel(text="Editor de Arquivos", font_style="Subtitle1")
        tb.add_widget(self.file_lbl)
        tb.add_widget(MDIconButton(icon="content-save", theme_text_color="Custom",
                                   text_color=COR_PROMPT, on_release=self.save_file))
        tb.add_widget(MDIconButton(icon="arrow-left",
                                   on_release=lambda x: MDApp.get_running_app().set_screen("page_1")))
        pr = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4), padding=dp(4))
        self.path_inp = TextInput(hint_text="Caminho do arquivo",
                                  hint_text_color=(0.38,0.38,0.38,1), multiline=False,
                                  background_color=COR_FUNDO_INPUT, foreground_color=COR_TEXTO,
                                  cursor_color=COR_PROMPT, font_size="12sp")
        pr.add_widget(self.path_inp)
        pr.add_widget(MDRaisedButton(text="Abrir", size_hint_x=None, width=dp(80),
                                     on_release=self.open_file))
        self.editor = TextInput(text="", multiline=True, background_color=COR_FUNDO,
                                foreground_color=COR_TEXTO, cursor_color=COR_PROMPT, font_size="13sp")
        self.msg = MDLabel(text="", halign="center", size_hint_y=None, height=dp(28),
                           theme_text_color="Secondary", font_style="Caption")
        layout.add_widget(tb); layout.add_widget(pr)
        layout.add_widget(self.editor); layout.add_widget(self.msg)
        self.add_widget(layout)

    def open_file(self, *a):
        p = self.path_inp.text.strip()
        if not p: show_toast(self.msg,"Informe o caminho."); return
        try:
            with open(p,"r",errors="replace") as f: self.editor.text = f.read()
            self.current_file = p
            self.file_lbl.text = os.path.basename(p)
            show_toast(self.msg, f"Aberto: {p}")
        except Exception as e: show_toast(self.msg, f"Erro: {e}")

    def save_file(self, *a):
        if not self.current_file: show_toast(self.msg,"Abra um arquivo primeiro."); return
        try:
            with open(self.current_file,"w") as f: f.write(self.editor.text)
            show_toast(self.msg, f"Salvo: {self.current_file}")
        except Exception as e: show_toast(self.msg, f"Erro: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
class MainApp(MDApp):
    terminal_count  = 1
    mod_python      = False
    mod_node        = False
    mod_git         = False
    mod_file_editor = False

    def build(self):
        # 1. Caminhos persistentes PRIMEIRO
        _init_paths(self.user_data_dir)

        # 2. Auth
        self.auth = FirebaseAuth()

        self.theme_cls.theme_style     = "Dark"
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.accent_palette  = "BlueGray"

        # 3. ScreenManager com FadeTransition entre splash/auth/main
        self.sm = ScreenManager(transition=FadeTransition(duration=0.25))

        # Splash
        self.splash = SplashScreen()
        self.sm.add_widget(self.splash)

        # Auth
        self.auth_screen = AuthScreen(self.auth, name="auth")
        self.sm.add_widget(self.auth_screen)

        # Telas principais (adicionadas agora, navegacao depois)
        self.sm.add_widget(TerminalScreen(1, name="page_1"))
        self.sm.add_widget(StoreScreen(name="store"))
        self.sm.add_widget(ExportScreen(name="export"))
        self.sm.add_widget(PythonEditorScreen(name="python_editor"))
        self.sm.add_widget(PythonConsoleScreen(name="python_console"))
        self.sm.add_widget(NodeReplScreen(name="node_repl"))
        self.sm.add_widget(GitHelperScreen(name="git_helper"))
        self.sm.add_widget(FileEditorScreen(name="file_editor"))
        self.sm.add_widget(VersionManagerScreen(name="version_manager"))

        # Toolbar + Drawer (criados mas so visiveis apos splash)
        self.root_layout = BoxLayout(orientation='vertical')
        self.toolbar = MDTopAppBar(
            title=f"Fox Terminal {VERSION}",
            left_action_items=[["menu", lambda x: self.toggle_drawer()]],
            right_action_items=[
                ["plus-box",        lambda x: self.add_terminal()],
                ["package-variant", lambda x: self.set_screen("version_manager")],
                ["export",          lambda x: self.set_screen("export")],
                ["account",         lambda x: self.set_screen("auth")],
            ]
        )
        self.nav_drawer = MDNavigationDrawer()
        self.menu_list  = MDList()
        self.update_menu()
        self.nav_drawer.add_widget(self.menu_list)

        self.root_layout.add_widget(self.toolbar)
        self.root_layout.add_widget(self.sm)

        ui = FloatLayout()
        ui.add_widget(self.root_layout)
        ui.add_widget(self.nav_drawer)

        # Inicia splash -> auth ou main
        Clock.schedule_once(lambda dt: self.splash.start(self._after_splash), 0.1)

        return ui

    def _after_splash(self):
        if self.auth.logged_in:
            self.go_main()
        else:
            self.sm.current = "auth"

    def go_main(self):
        """Vai para o terminal principal apos login ou skip."""
        self.sm.current = "page_1"
        self.update_menu()

    def toggle_drawer(self):
        state = "open" if self.nav_drawer.state == "close" else "close"
        self.nav_drawer.set_state(state)

    def add_terminal(self):
        self.terminal_count += 1
        name = f"page_{self.terminal_count}"
        self.sm.add_widget(TerminalScreen(self.terminal_count, name=name))
        self.update_menu()
        self.set_screen(name)

    def activate_mod(self, screen_name):
        mapping = {
            "python_editor": "mod_python",
            "node_repl":     "mod_node",
            "git_helper":    "mod_git",
            "file_editor":   "mod_file_editor",
        }
        if screen_name in mapping:
            setattr(self, mapping[screen_name], True)
            save_mod({"name": screen_name, "version": "1.0", "author": "Fox Terminal"})
            self.update_menu()
            self.set_screen(screen_name)

    def update_menu(self):
        self.menu_list.clear_widgets()

        # Cabecalho com usuario logado
        user_txt = f"  {self.auth.email}" if self.auth.logged_in else "  (offline)"
        self.menu_list.add_widget(MDLabel(
            text=f"  Fox Terminal  {VERSION}\n{user_txt}",
            size_hint_y=None, height=dp(64), font_style="Caption",
        ))

        for label, icon, screen in [
            ("Nova Aba Terminal",  "plus",            None),
            ("Loja de Mods",       "store",           "store"),
            ("Exportar Mods",      "export",          "export"),
            ("Versoes de Pacotes", "package-variant", "version_manager"),
            ("Conta / Login",      "account",         "auth"),
        ]:
            if screen is None:
                it = OneLineIconListItem(text=label, on_release=lambda x: self.add_terminal())
            else:
                it = OneLineIconListItem(text=label, on_release=lambda x,s=screen: self.set_screen(s))
            it.add_widget(IconLeftWidget(icon=icon))
            self.menu_list.add_widget(it)

        for i in range(1, self.terminal_count+1):
            t = OneLineIconListItem(
                text=f"Terminal {i}",
                on_release=lambda x, n=f"page_{i}": self.set_screen(n)
            )
            t.add_widget(IconLeftWidget(icon="console"))
            self.menu_list.add_widget(t)

        for ativo, label, icon, screen in [
            (self.mod_python,      "Python Editor",      "language-python",     "python_editor"),
            (self.mod_node,        "Node.js REPL",       "language-javascript", "node_repl"),
            (self.mod_git,         "Git Helper",         "git",                 "git_helper"),
            (self.mod_file_editor, "Editor de Arquivos", "file-code",           "file_editor"),
        ]:
            if ativo:
                it = OneLineIconListItem(text=label, on_release=lambda x,s=screen: self.set_screen(s))
                it.add_widget(IconLeftWidget(icon=icon))
                self.menu_list.add_widget(it)

    def set_screen(self, name):
        if name and self.sm.has_screen(name):
            self.sm.current = name
        self.nav_drawer.set_state("close")


if __name__ == "__main__":
    MainApp().run()
