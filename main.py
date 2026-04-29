import sys
import io
import os
import subprocess
import threading
import json
import zipfile
import shutil

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivy.uix.screenmanager import ScreenManager, NoTransition
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
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.utils import platform

Window.softinput_mode = 'below_target'

VERSION      = "v1.32.0-beta"
HISTORY_FILE = "fox_history.json"
MODS_FILE    = "fox_mods.json"
ALIAS_FILE   = "fox_alias.json"
ENV_FILE     = "fox_env.json"

if platform == "android":
    try:
        from android.storage import primary_external_storage_path
        EXPORT_DIR = os.path.join(primary_external_storage_path(), "FoxTerminal", "exports")
    except Exception:
        EXPORT_DIR = os.path.join(os.path.expanduser("~"), "FoxTerminal", "exports")
else:
    EXPORT_DIR = os.path.join(os.path.expanduser("~"), "FoxTerminal", "exports")

COR_FUNDO       = (0.08, 0.08, 0.10, 1)
COR_FUNDO_INPUT = (0.12, 0.12, 0.15, 1)
COR_TEXTO       = (0.85, 0.90, 0.85, 1)
COR_PROMPT      = (0.45, 0.80, 0.55, 1)
COR_ERRO        = (0.85, 0.45, 0.45, 1)
COR_BARRA       = (0.10, 0.10, 0.14, 1)


# ─── Catalogo completo de pacotes/versoes ─────────────────────────────────────
# Formato: { "Pacote": [ ("versao", "comando de instalacao") ] }
CATALOGO = {
    "Python": [
        ("3.8.18",  "pkg install python"),
        ("3.9.18",  "pkg install python"),
        ("3.10.13", "pkg install python"),
        ("3.11.8",  "pkg install python"),
        ("3.12.2",  "pkg install python"),
        ("3.13.2",  "python3 --version  (ja instalado no Pydroid)"),
    ],
    "Node.js": [
        ("14.21.3", "pkg install nodejs-lts"),
        ("16.20.2", "pkg install nodejs-lts"),
        ("18.19.1", "pkg install nodejs-lts"),
        ("20.11.1", "pkg install nodejs"),
        ("21.6.2",  "pkg install nodejs"),
        ("22.0.0",  "nvm install 22  (via nvm)"),
    ],
    "Git": [
        ("2.30.0", "pkg install git"),
        ("2.35.0", "pkg install git"),
        ("2.40.1", "pkg install git"),
        ("2.43.0", "pkg install git"),
        ("2.44.0", "apt install git  (Linux/Termux)"),
    ],
    "pip": [
        ("22.0",   "python -m pip install --upgrade pip"),
        ("23.0",   "python -m pip install --upgrade pip"),
        ("23.3",   "python -m pip install --upgrade pip"),
        ("24.0",   "python -m pip install --upgrade pip"),
    ],
    "npm": [
        ("8.19.4",  "npm install -g npm@8"),
        ("9.9.3",   "npm install -g npm@9"),
        ("10.5.0",  "npm install -g npm@10"),
    ],
    "Termux (Android)": [
        ("pkg",    "apt update && apt upgrade"),
        ("clang",  "pkg install clang"),
        ("cmake",  "pkg install cmake"),
        ("curl",   "pkg install curl"),
        ("wget",   "pkg install wget"),
        ("openssh","pkg install openssh"),
        ("vim",    "pkg install vim"),
        ("nano",   "pkg install nano"),
        ("ffmpeg", "pkg install ffmpeg"),
    ],
    "Kivy": [
        ("2.1.0", "pip install kivy==2.1.0"),
        ("2.2.1", "pip install kivy==2.2.1"),
        ("2.3.0", "pip install kivy==2.3.0"),
        ("2.3.1", "pip install kivy==2.3.1"),
    ],
    "KivyMD": [
        ("1.1.1", "pip install kivymd==1.1.1"),
        ("1.2.0", "pip install kivymd==1.2.0"),
        ("2.0.0", "pip install https://github.com/kivymd/KivyMD/archive/master.zip"),
    ],
    "Ruby": [
        ("3.1.4", "pkg install ruby"),
        ("3.2.3", "pkg install ruby"),
        ("3.3.0", "pkg install ruby"),
    ],
    "Lua": [
        ("5.3.6", "pkg install lua53"),
        ("5.4.6", "pkg install lua54"),
    ],
    "Rust": [
        ("1.75.0", "pkg install rust"),
        ("1.77.0", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"),
    ],
    "Go": [
        ("1.21.0", "pkg install golang"),
        ("1.22.0", "pkg install golang"),
    ],
    "Java (OpenJDK)": [
        ("11", "pkg install openjdk-11"),
        ("17", "pkg install openjdk-17"),
        ("21", "pkg install openjdk-21"),
    ],
    "SQLite": [
        ("3.40.0", "pkg install sqlite"),
        ("3.45.0", "pkg install sqlite"),
    ],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────
def show_toast(label_widget, msg, duration=3.0):
    label_widget.text = msg
    Clock.schedule_once(lambda dt: setattr(label_widget, 'text', ''), duration)


def colored_box(color, **kwargs):
    box = BoxLayout(**kwargs)
    with box.canvas.before:
        Color(*color)
        rect = Rectangle(size=box.size, pos=box.pos)
    box.bind(
        size=lambda w, v: setattr(rect, 'size', v),
        pos=lambda w, v: setattr(rect, 'pos', v)
    )
    return box


# ─── Widget de saida do terminal (SEM CodeInput — corrige bug Select All) ─────
class TerminalOutput(ScrollView):
    """
    ScrollView com um TextInput readonly de fundo escuro.
    Substituimos CodeInput para eliminar o bug de 'Select All'
    que aparecia ao toque simples no Android.
    """
    def __init__(self, initial_text="", **kwargs):
        super().__init__(**kwargs)
        self._label = TextInput(
            text=initial_text,
            readonly=True,
            multiline=True,
            background_color=COR_FUNDO,
            foreground_color=COR_TEXTO,
            font_size="13sp",
            size_hint_y=None,
        )
        # Ajusta altura automaticamente ao conteudo
        self._label.bind(minimum_height=self._label.setter('height'))
        self.add_widget(self._label)
        # Rola para o fim ao atualizar
        self._label.bind(text=self._scroll_end)

    def _scroll_end(self, instance, value):
        Clock.schedule_once(lambda dt: setattr(self, 'scroll_y', 0), 0.05)

    @property
    def text(self):
        return self._label.text

    @text.setter
    def text(self, value):
        self._label.text = value

    def append(self, value):
        self._label.text += value


# ─── Persistencia ─────────────────────────────────────────────────────────────
def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def _save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def load_history():   return _load_json(HISTORY_FILE, [])
def save_history(h):  _save_json(HISTORY_FILE, h[-200:])
def load_mods():      return _load_json(MODS_FILE, [])
def load_aliases():   return _load_json(ALIAS_FILE, {})
def save_aliases(a):  _save_json(ALIAS_FILE, a)
def load_env():       return _load_json(ENV_FILE, {})
def save_env(e):      _save_json(ENV_FILE, e)

def save_mod(mod_dict):
    mods = load_mods()
    mods = [m for m in mods if m.get("name") != mod_dict.get("name")]
    mods.append(mod_dict)
    _save_json(MODS_FILE, mods)


# ─── Ajuda do terminal ────────────────────────────────────────────────────────
AJUDA = f"""Fox Terminal {VERSION} - Comandos internos
--------------------------------------
  clear / cls        Limpa a tela
  cd <pasta>         Muda de diretorio
  pwd                Mostra diretorio atual
  ls                 Lista arquivos
  cat <arquivo>      Mostra conteudo
  mkdir <pasta>      Cria pasta
  rm <arquivo>       Remove arquivo
  cp <orig> <dest>   Copia arquivo
  mv <orig> <dest>   Move / renomeia
  echo <texto>       Imprime texto
  env                Lista variaveis de ambiente
  set VAR=valor      Define variavel
  unset VAR          Remove variavel
  alias              Lista aliases
  alias nome=cmd     Define alias
  unalias nome       Remove alias
  history            Historico de comandos
  help               Esta ajuda
  exit / quit        Fecha o app
--------------------------------------
Outros comandos sao executados pelo
sistema operacional normalmente.
"""


# ─── Terminal ─────────────────────────────────────────────────────────────────
class TerminalScreen(MDScreen):
    def __init__(self, page_num, **kwargs):
        super().__init__(**kwargs)
        self.name          = f"page_{page_num}"
        self.page_num      = page_num
        self.cwd           = os.path.expanduser("~")
        self.cmd_history   = load_history()
        self.history_index = len(self.cmd_history)
        self.process       = None
        self.aliases       = load_aliases()
        self.env_vars      = load_env()

        layout = BoxLayout(orientation='vertical')

        self.progress = MDProgressBar(
            value=0, size_hint_y=None, height="3dp", opacity=0
        )

        # TerminalOutput substitui CodeInput — sem bug de Select All
        self.output = TerminalOutput(
            initial_text=(
                f"Fox Terminal {VERSION}\n"
                f"Terminal {page_num}  |  {self.cwd}\n"
                f"Digite 'help' para ver os comandos.\n"
                f"$ "
            )
        )

        input_row = BoxLayout(size_hint_y=None, height="48dp", spacing="2dp")

        self.input = TextInput(
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            hint_text="Comando...",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            font_size="14sp",
        )
        self.input.bind(on_text_validate=self.process_command)

        btn_up    = MDIconButton(icon="arrow-up",    size_hint_x=None, width="44dp",
                                 on_release=lambda x: self.nav_history(-1))
        btn_down  = MDIconButton(icon="arrow-down",  size_hint_x=None, width="44dp",
                                 on_release=lambda x: self.nav_history(1))
        btn_stop  = MDIconButton(icon="stop-circle", size_hint_x=None, width="44dp",
                                 theme_text_color="Custom", text_color=COR_ERRO,
                                 on_release=self.stop_process)
        btn_clear = MDIconButton(icon="broom",       size_hint_x=None, width="44dp",
                                 on_release=self.clear_output)

        input_row.add_widget(self.input)
        input_row.add_widget(btn_up)
        input_row.add_widget(btn_down)
        input_row.add_widget(btn_stop)
        input_row.add_widget(btn_clear)

        layout.add_widget(self.progress)
        layout.add_widget(self.output)
        layout.add_widget(input_row)
        self.add_widget(layout)

    def nav_history(self, direction):
        if not self.cmd_history:
            return
        self.history_index = max(
            0, min(len(self.cmd_history) - 1, self.history_index + direction)
        )
        self.input.text = self.cmd_history[self.history_index]

    def write(self, text):
        self.output.append(text)

    def process_command(self, instance):
        raw = self.input.text.strip()
        self.input.text = ""
        if not raw:
            return

        parts = raw.split(None, 1)
        if parts[0] in self.aliases:
            raw = self.aliases[parts[0]] + ("" if len(parts) == 1 else " " + parts[1])

        for k, v in self.env_vars.items():
            raw = raw.replace(f"${k}", v)

        if not self.cmd_history or self.cmd_history[-1] != raw:
            self.cmd_history.append(raw)
            save_history(self.cmd_history)
        self.history_index = len(self.cmd_history)

        self.write(f"$ {raw}\n")
        self._handle(raw)

    def _handle(self, cmd):
        parts = cmd.split()
        base  = parts[0] if parts else ""

        if cmd in ("clear", "cls"):
            self.clear_output(None); return
        elif cmd in ("help", "--help"):
            self.write(AJUDA)
        elif cmd == "pwd":
            self.write(self.cwd + "\n")
        elif base == "cd":
            self._cd(cmd[2:].strip() or os.path.expanduser("~"))
        elif base == "ls":
            self._ls(parts[1] if len(parts) > 1 else ".")
        elif base == "cat":
            self._cat(parts[1]) if len(parts) > 1 else self.write("[erro] uso: cat <arquivo>\n")
        elif base == "mkdir":
            self._mkdir(parts[1]) if len(parts) > 1 else self.write("[erro] uso: mkdir <pasta>\n")
        elif base == "rm":
            self._rm(parts[1]) if len(parts) > 1 else self.write("[erro] uso: rm <arquivo>\n")
        elif base == "cp":
            self._cp(parts[1], parts[2]) if len(parts) > 2 else self.write("[erro] uso: cp <orig> <dest>\n")
        elif base == "mv":
            self._mv(parts[1], parts[2]) if len(parts) > 2 else self.write("[erro] uso: mv <orig> <dest>\n")
        elif base == "echo":
            self.write(" ".join(parts[1:]) + "\n")
        elif cmd == "env":
            [self.write(f"  {k}={v}\n") for k, v in self.env_vars.items()] or self.write("Nenhuma variavel.\n")
        elif base == "set" and "=" in cmd:
            k, _, v = cmd[4:].strip().partition("=")
            self.env_vars[k.strip()] = v.strip(); save_env(self.env_vars)
            self.write(f"  {k.strip()} = {v.strip()}\n")
        elif base == "unset":
            self.env_vars.pop(parts[1], None); save_env(self.env_vars)
            self.write(f"  {parts[1]} removida.\n") if len(parts) > 1 else self.write("[erro] uso: unset VAR\n")
        elif base == "alias" and "=" in cmd:
            k, _, v = cmd[5:].strip().partition("=")
            self.aliases[k.strip()] = v.strip(); save_aliases(self.aliases)
            self.write(f"  alias {k.strip()} = '{v.strip()}'\n")
        elif cmd == "alias":
            [self.write(f"  {k} = '{v}'\n") for k, v in self.aliases.items()] or self.write("Nenhum alias.\n")
        elif base == "unalias":
            self.aliases.pop(parts[1], None); save_aliases(self.aliases)
            self.write(f"  alias '{parts[1]}' removido.\n") if len(parts) > 1 else None
        elif cmd == "history":
            [self.write(f"  {i:>3}  {h}\n") for i, h in enumerate(self.cmd_history[-30:], 1)]
        elif cmd in ("exit", "quit"):
            MDApp.get_running_app().stop(); return
        else:
            self.progress.opacity = 1
            env = os.environ.copy(); env.update(self.env_vars)
            threading.Thread(target=self.run_sys, args=(cmd, env), daemon=True).start()
            return

        self.write("$ ")

    def _abs(self, path):
        return os.path.normpath(
            os.path.join(self.cwd, path) if not os.path.isabs(path) else path
        )

    def _cd(self, path):
        new = self._abs("~" if path == "~" else path)
        if path == "~":
            new = os.path.expanduser("~")
        if os.path.isdir(new):
            self.cwd = new; self.write(f"-> {self.cwd}\n")
        else:
            self.write(f"cd: '{path}': nao encontrado\n")

    def _ls(self, path):
        try:
            items = sorted(os.listdir(self._abs(path)))
            for i in items:
                tag = "[D]" if os.path.isdir(os.path.join(self._abs(path), i)) else "[F]"
                self.write(f"  {tag} {i}\n")
            if not items:
                self.write("(pasta vazia)\n")
        except Exception as e:
            self.write(f"[erro] {e}\n")

    def _cat(self, f):
        try:
            with open(self._abs(f), "r", errors="replace") as fh:
                c = fh.read()
            self.write(c if c.endswith("\n") else c + "\n")
        except Exception as e:
            self.write(f"[erro] {e}\n")

    def _mkdir(self, name):
        try:
            os.makedirs(self._abs(name), exist_ok=True)
            self.write(f"Criado: {self._abs(name)}\n")
        except Exception as e:
            self.write(f"[erro] {e}\n")

    def _rm(self, name):
        p = self._abs(name)
        try:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            self.write(f"Removido: {p}\n")
        except Exception as e:
            self.write(f"[erro] {e}\n")

    def _cp(self, src, dst):
        try:
            shutil.copy2(self._abs(src), self._abs(dst))
            self.write(f"Copiado: {self._abs(src)} -> {self._abs(dst)}\n")
        except Exception as e:
            self.write(f"[erro] {e}\n")

    def _mv(self, src, dst):
        try:
            shutil.move(self._abs(src), self._abs(dst))
            self.write(f"Movido: {self._abs(src)} -> {self._abs(dst)}\n")
        except Exception as e:
            self.write(f"[erro] {e}\n")

    def run_sys(self, cmd, env):
        try:
            self.process = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=self.cwd, env=env
            )
            out, err = self.process.communicate(timeout=60)
            Clock.schedule_once(lambda dt: self.done(out, err, self.process.returncode))
        except subprocess.TimeoutExpired:
            self.process.kill()
            Clock.schedule_once(lambda dt: self.done("", "Tempo limite (60s) excedido\n", 1))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.done("", str(e), 1))
        finally:
            self.process = None

    def done(self, out, err, code):
        if out: self.write(out)
        if err: self.write(f"[erro] {err}\n")
        self.write(f"{'[ok]' if code == 0 else f'[falhou: {code}]'}\n$ ")
        self.progress.opacity = 0

    def stop_process(self, instance):
        if self.process:
            try: self.process.kill(); self.write("\n[processo encerrado]\n$ ")
            except Exception: pass
        else:
            self.write("[sem processo ativo]\n$ ")

    def clear_output(self, instance):
        self.output.text = f"Fox Terminal {VERSION}  |  Terminal {self.page_num}\n$ "


# ─── Gerenciador de Versoes (com busca e catalogo completo) ───────────────────
class VersionManagerScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_items = []  # lista de (pkg, versao, cmd)
        self._build_index()

        layout = BoxLayout(orientation='vertical', padding="8dp", spacing="6dp")

        layout.add_widget(MDLabel(
            text="Versoes e Pacotes",
            font_style="H6", halign="center",
            size_hint_y=None, height="44dp"
        ))

        # Barra de pesquisa
        search_row = BoxLayout(size_hint_y=None, height="44dp", spacing="6dp")
        self.search_input = TextInput(
            hint_text="Pesquisar pacote ou versao...",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="14sp",
        )
        self.search_input.bind(text=self.on_search)
        btn_clear_search = MDIconButton(
            icon="close-circle",
            size_hint_x=None, width="44dp",
            on_release=lambda x: setattr(self.search_input, 'text', '')
        )
        search_row.add_widget(self.search_input)
        search_row.add_widget(btn_clear_search)
        layout.add_widget(search_row)

        # Contador de resultados
        self.count_label = MDLabel(
            text=f"{len(self.all_items)} pacotes no catalogo",
            font_style="Caption", halign="center",
            size_hint_y=None, height="24dp",
            theme_text_color="Secondary"
        )
        layout.add_widget(self.count_label)

        # Lista de resultados
        self.scroll = ScrollView()
        self.pkg_list = MDList()
        self.scroll.add_widget(self.pkg_list)
        layout.add_widget(self.scroll)

        # Detalhe do comando de instalacao
        self.detail_label = TextInput(
            text="Toque em um item para ver o comando de instalacao.",
            readonly=True,
            multiline=True,
            size_hint_y=None, height="72dp",
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_PROMPT,
            font_size="12sp",
        )
        layout.add_widget(self.detail_label)

        layout.add_widget(MDRaisedButton(
            text="Voltar",
            pos_hint={"center_x": .5},
            size_hint_y=None, height="44dp",
            on_release=lambda x: MDApp.get_running_app().set_screen("page_1")
        ))

        self.add_widget(layout)
        self._populate(self.all_items)

    def _build_index(self):
        for pkg, entries in CATALOGO.items():
            for versao, cmd in entries:
                self.all_items.append((pkg, versao, cmd))

    def _populate(self, items):
        self.pkg_list.clear_widgets()
        if not items:
            self.pkg_list.add_widget(MDLabel(
                text="Nenhum resultado encontrado.",
                halign="center", size_hint_y=None, height="48dp",
                theme_text_color="Secondary"
            ))
            return
        for pkg, versao, cmd in items:
            item = OneLineIconListItem(
                text=f"{pkg}   {versao}",
                on_release=lambda x, p=pkg, v=versao, c=cmd: self._show_detail(p, v, c)
            )
            item.add_widget(IconLeftWidget(icon="package-variant"))
            self.pkg_list.add_widget(item)
        self.count_label.text = f"{len(items)} resultado(s)"

    def _show_detail(self, pkg, versao, cmd):
        self.detail_label.text = f"{pkg} {versao}\nInstalar: {cmd}"

    def on_search(self, instance, value):
        q = value.strip().lower()
        if not q:
            self._populate(self.all_items)
            return
        filtered = [
            (p, v, c) for p, v, c in self.all_items
            if q in p.lower() or q in v.lower() or q in c.lower()
        ]
        self._populate(filtered)


# ─── Editor de Arquivos ───────────────────────────────────────────────────────
class FileEditorScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_file = None
        layout = BoxLayout(orientation='vertical')

        toolbar = colored_box(
            COR_BARRA, size_hint_y=None, height="48dp",
            padding="4dp", spacing="4dp"
        )
        self.file_label = MDLabel(text="Editor de Arquivos", font_style="Subtitle1")
        toolbar.add_widget(self.file_label)
        toolbar.add_widget(MDIconButton(
            icon="content-save",
            theme_text_color="Custom", text_color=COR_PROMPT,
            on_release=self.save_file
        ))
        toolbar.add_widget(MDIconButton(
            icon="arrow-left",
            on_release=lambda x: MDApp.get_running_app().set_screen("page_1")
        ))

        path_row = BoxLayout(size_hint_y=None, height="44dp", spacing="4dp", padding="4dp")
        self.path_input = TextInput(
            hint_text="Caminho do arquivo (ex: /sdcard/test.py)",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="12sp",
        )
        btn_open = MDRaisedButton(
            text="Abrir",
            size_hint_x=None, width="80dp",
            on_release=self.open_file
        )
        path_row.add_widget(self.path_input)
        path_row.add_widget(btn_open)

        self.editor = TextInput(
            text="",
            multiline=True,
            background_color=COR_FUNDO,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="13sp",
        )

        self.msg = MDLabel(
            text="", halign="center",
            size_hint_y=None, height="28dp",
            theme_text_color="Secondary", font_style="Caption"
        )

        layout.add_widget(toolbar)
        layout.add_widget(path_row)
        layout.add_widget(self.editor)
        layout.add_widget(self.msg)
        self.add_widget(layout)

    def open_file(self, instance):
        path = self.path_input.text.strip()
        if not path:
            show_toast(self.msg, "Informe o caminho do arquivo.")
            return
        try:
            with open(path, "r", errors="replace") as f:
                self.editor.text = f.read()
            self.current_file = path
            self.file_label.text = os.path.basename(path)
            show_toast(self.msg, f"Aberto: {path}")
        except Exception as e:
            show_toast(self.msg, f"Erro: {e}")

    def save_file(self, instance):
        if not self.current_file:
            show_toast(self.msg, "Abra um arquivo primeiro.")
            return
        try:
            with open(self.current_file, "w") as f:
                f.write(self.editor.text)
            show_toast(self.msg, f"Salvo: {self.current_file}")
        except Exception as e:
            show_toast(self.msg, f"Erro: {e}")


# ─── Node.js REPL ─────────────────────────────────────────────────────────────
class NodeReplScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')

        toolbar = colored_box(
            COR_BARRA, size_hint_y=None, height="48dp",
            padding="4dp", spacing="4dp"
        )
        toolbar.add_widget(MDLabel(text="Node.js REPL", font_style="Subtitle1"))
        toolbar.add_widget(MDIconButton(
            icon="arrow-left",
            on_release=lambda x: MDApp.get_running_app().set_screen("store")
        ))

        self.output = TerminalOutput(
            initial_text="Node.js REPL\nVerificando node...\n"
        )

        input_row = BoxLayout(size_hint_y=None, height="48dp", spacing="4dp")
        self.input = TextInput(
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            hint_text="Expressao JS...",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            font_size="14sp",
        )
        self.input.bind(on_text_validate=self.run_js)
        btn_run = MDIconButton(
            icon="play",
            theme_text_color="Custom", text_color=COR_PROMPT,
            on_release=self.run_js
        )
        input_row.add_widget(self.input)
        input_row.add_widget(btn_run)

        layout.add_widget(toolbar)
        layout.add_widget(self.output)
        layout.add_widget(input_row)
        self.add_widget(layout)

        Clock.schedule_once(lambda dt: threading.Thread(
            target=self._check_node, daemon=True).start(), 0.5)

    def _check_node(self):
        try:
            r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
            v = r.stdout.strip()
            Clock.schedule_once(lambda dt: setattr(
                self.output, 'text',
                f"Node.js {v} encontrado.\nDigite uma expressao JS.\n> "
            ))
        except Exception:
            Clock.schedule_once(lambda dt: setattr(
                self.output, 'text',
                "Node.js nao encontrado.\n"
                "Instale com: pkg install nodejs\n"
                "Ou veja Versoes de Pacotes para o comando correto.\n"
            ))

    def run_js(self, instance):
        code = self.input.text.strip()
        self.input.text = ""
        if not code:
            return
        self.output.append(f"> {code}\n")
        threading.Thread(target=self._exec_js, args=(code,), daemon=True).start()

    def _exec_js(self, code):
        try:
            r = subprocess.run(
                ["node", "-e", f"try{{console.log(eval({json.dumps(code)}))}}catch(e){{console.error(e.message)}}"],
                capture_output=True, text=True, timeout=10
            )
            out = (r.stdout or r.stderr or "(sem saida)").strip()
            Clock.schedule_once(lambda dt: self.output.append(f"{out}\n> "))
        except FileNotFoundError:
            Clock.schedule_once(lambda dt: self.output.append("[erro] node nao encontrado\n"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.output.append(f"[erro] {e}\n"))


# ─── Git Helper ───────────────────────────────────────────────────────────────
class GitHelperScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')

        toolbar = colored_box(
            COR_BARRA, size_hint_y=None, height="48dp",
            padding="4dp", spacing="4dp"
        )
        toolbar.add_widget(MDLabel(text="Git Helper", font_style="Subtitle1"))
        toolbar.add_widget(MDIconButton(
            icon="arrow-left",
            on_release=lambda x: MDApp.get_running_app().set_screen("store")
        ))

        self.output = TerminalOutput(initial_text="Git Helper\n")

        scroll = ScrollView(size_hint_y=None, height="200dp")
        btn_list = MDList()

        comandos = [
            ("git",           "git status",                 "Status do repositorio"),
            ("source-branch", "git log --oneline -10",      "Ultimos 10 commits"),
            ("plus",          "git add .",                  "Adicionar tudo"),
            ("check",         "git commit -m 'Fox commit'", "Commit rapido"),
            ("upload",        "git push",                   "Push para remoto"),
            ("download",      "git pull",                   "Pull do remoto"),
            ("source-fork",   "git clone",                  "Clonar repositorio"),
            ("delete",        "git stash",                  "Stash (guardar mudancas)"),
            ("tag",           "git tag",                    "Listar tags"),
            ("history",       "git diff",                   "Ver diferencas"),
        ]

        for icon, cmd, desc in comandos:
            item = OneLineIconListItem(
                text=desc,
                on_release=lambda x, c=cmd: self.run_git(c)
            )
            item.add_widget(IconLeftWidget(icon=icon))
            btn_list.add_widget(item)

        scroll.add_widget(btn_list)

        path_row = BoxLayout(size_hint_y=None, height="44dp", spacing="4dp", padding="4dp")
        self.path_input = TextInput(
            hint_text="Caminho do repositorio (deixe vazio para home)",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="12sp",
        )
        path_row.add_widget(self.path_input)

        cmd_row = BoxLayout(size_hint_y=None, height="44dp", spacing="4dp", padding="4dp")
        self.cmd_input = TextInput(
            hint_text="git <seu comando>",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="13sp",
        )
        self.cmd_input.bind(on_text_validate=lambda x: self.run_git(self.cmd_input.text))
        btn_exec = MDRaisedButton(
            text="Executar",
            size_hint_x=None, width="100dp",
            on_release=lambda x: self.run_git(self.cmd_input.text)
        )
        cmd_row.add_widget(self.cmd_input)
        cmd_row.add_widget(btn_exec)

        layout.add_widget(toolbar)
        layout.add_widget(scroll)
        layout.add_widget(path_row)
        layout.add_widget(cmd_row)
        layout.add_widget(self.output)
        self.add_widget(layout)

    def run_git(self, cmd):
        cwd = self.path_input.text.strip() or os.path.expanduser("~")
        self.output.append(f"\n$ {cmd}\n")
        threading.Thread(target=self._exec, args=(cmd, cwd), daemon=True).start()

    def _exec(self, cmd, cwd):
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, cwd=cwd, timeout=30
            )
            out = r.stdout or r.stderr or "(sem saida)"
            Clock.schedule_once(lambda dt: self.output.append(out))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.output.append(f"[erro] {e}\n"))


# ─── Python Editor ────────────────────────────────────────────────────────────
class PythonEditorScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')

        toolbar = colored_box(
            COR_BARRA, size_hint_y=None, height="48dp",
            padding="4dp", spacing="4dp"
        )
        toolbar.add_widget(MDLabel(text="Python Editor", font_style="Subtitle1"))
        toolbar.add_widget(MDIconButton(
            icon="play",
            theme_text_color="Custom", text_color=COR_PROMPT,
            on_release=self.run_code
        ))
        toolbar.add_widget(MDIconButton(
            icon="delete-outline",
            theme_text_color="Custom", text_color=COR_ERRO,
            on_release=self.clear_code
        ))
        toolbar.add_widget(MDIconButton(
            icon="arrow-left",
            on_release=lambda x: MDApp.get_running_app().set_screen("store")
        ))

        self.code_input = TextInput(
            text='# Fox Terminal - Python Editor\n\nprint("Ola, Fox Terminal!")\n',
            multiline=True,
            background_color=COR_FUNDO,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="14sp",
        )

        layout.add_widget(toolbar)
        layout.add_widget(self.code_input)
        self.add_widget(layout)

    def run_code(self, instance):
        app = MDApp.get_running_app()
        app.sm.get_screen("python_console").run_and_show(self.code_input.text)
        app.set_screen("python_console")

    def clear_code(self, instance):
        self.code_input.text = ""


# ─── Python Console ───────────────────────────────────────────────────────────
class PythonConsoleScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')

        toolbar = colored_box(
            COR_BARRA, size_hint_y=None, height="48dp", padding="4dp"
        )
        toolbar.add_widget(MDLabel(text="Saida Python", font_style="Subtitle1"))
        toolbar.add_widget(MDIconButton(
            icon="arrow-left",
            on_release=lambda x: MDApp.get_running_app().set_screen("python_editor")
        ))

        self.console_output = TerminalOutput(initial_text="")

        layout.add_widget(toolbar)
        layout.add_widget(self.console_output)
        self.add_widget(layout)

    def run_and_show(self, code):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        try:
            exec(compile(code, "<fox_editor>", "exec"), {})
            out = sys.stdout.getvalue()
            self.console_output.text = out if out else "(sem saida)"
        except Exception:
            import traceback
            self.console_output.text = f"Erro:\n{traceback.format_exc()}"
        finally:
            sys.stdout, sys.stderr = old_out, old_err


# ─── Loja de Mods ─────────────────────────────────────────────────────────────
class StoreScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding="16dp", spacing="8dp")

        layout.add_widget(MDLabel(
            text="Loja de Mods",
            font_style="H5", halign="center",
            size_hint_y=None, height="48dp"
        ))

        self.msg_label = MDLabel(
            text="", halign="center",
            size_hint_y=None, height="28dp",
            theme_text_color="Secondary",
        )
        layout.add_widget(self.msg_label)

        scroll = ScrollView()
        self.list_view = MDList()

        mods = [
            ("language-python",     "Python Editor  -  editor e console Python",     "python_editor"),
            ("language-javascript", "Node.js REPL  -  execute JavaScript",            "node_repl"),
            ("git",                 "Git Helper  -  atalhos para Git",                "git_helper"),
            ("file-code",           "Editor de Arquivos  -  abrir e editar arquivos", "file_editor"),
        ]

        for icon, title, screen in mods:
            item = OneLineIconListItem(
                text=title,
                on_release=lambda x, s=screen, t=title: self.activate_mod(s, t)
            )
            item.add_widget(IconLeftWidget(icon=icon))
            self.list_view.add_widget(item)

        scroll.add_widget(self.list_view)
        layout.add_widget(scroll)

        btn_row = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        btn_row.add_widget(MDRaisedButton(
            text="Exportar Mods",
            on_release=lambda x: MDApp.get_running_app().set_screen("export")
        ))
        btn_row.add_widget(MDRaisedButton(
            text="Voltar",
            on_release=lambda x: MDApp.get_running_app().set_screen("page_1")
        ))
        layout.add_widget(btn_row)
        self.add_widget(layout)

    def activate_mod(self, screen_name, title):
        app = MDApp.get_running_app()
        app.activate_mod(screen_name)
        show_toast(self.msg_label, f"Mod ativado: {title.split('-')[0].strip()}")


# ─── Exportacao de Mods ───────────────────────────────────────────────────────
class ExportScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        outer = ScrollView()
        layout = BoxLayout(
            orientation='vertical', padding="16dp", spacing="10dp",
            size_hint_y=None
        )
        layout.bind(minimum_height=layout.setter('height'))

        layout.add_widget(MDLabel(
            text="Exportar Mod",
            font_style="H5", halign="center",
            size_hint_y=None, height="48dp"
        ))

        for label, attr, hint, default in [
            ("Nome do mod (sem espacos):", "field_name",    "meu_mod",     "meu_mod"),
            ("Versao:",                    "field_version", "1.0.0",       "1.0.0"),
            ("Autor (usuario GitHub):",    "field_author",  "seu_usuario", ""),
        ]:
            layout.add_widget(MDLabel(
                text=label, size_hint_y=None, height="28dp",
                theme_text_color="Secondary"
            ))
            field = TextInput(
                text=default, multiline=False,
                size_hint_y=None, height="44dp",
                background_color=COR_FUNDO_INPUT,
                foreground_color=COR_TEXTO,
                cursor_color=COR_PROMPT,
                hint_text=hint,
                hint_text_color=(0.38, 0.38, 0.38, 1),
                font_size="14sp",
            )
            setattr(self, attr, field)
            layout.add_widget(field)

        layout.add_widget(MDLabel(
            text="Descricao:", size_hint_y=None, height="28dp",
            theme_text_color="Secondary"
        ))
        self.field_desc = TextInput(
            text="", multiline=True,
            size_hint_y=None, height="80dp",
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            hint_text="O que este mod faz?",
            hint_text_color=(0.38, 0.38, 0.38, 1),
            font_size="13sp",
        )
        layout.add_widget(self.field_desc)

        self.result_label = MDLabel(
            text="", halign="center",
            size_hint_y=None, height="40dp",
            theme_text_color="Secondary", font_style="Caption"
        )
        layout.add_widget(self.result_label)

        btn_row = BoxLayout(size_hint_y=None, height="48dp", spacing="6dp")
        btn_row.add_widget(MDRaisedButton(text="Gerar .zip",           on_release=self.export_zip))
        btn_row.add_widget(MDRaisedButton(text="Instrucoes GitHub",    on_release=lambda x: self.show_github_instructions()))
        btn_row.add_widget(MDRaisedButton(text="Voltar",               on_release=lambda x: MDApp.get_running_app().set_screen("store")))
        layout.add_widget(btn_row)

        self.instructions = TextInput(
            text="",
            readonly=True,
            multiline=True,
            background_color=COR_FUNDO,
            foreground_color=COR_TEXTO,
            font_size="12sp",
            size_hint_y=None, height="300dp"
        )
        layout.add_widget(self.instructions)

        outer.add_widget(layout)
        self.add_widget(outer)

    def export_zip(self, instance):
        name    = self.field_name.text.strip().replace(" ", "_") or "meu_mod"
        version = self.field_version.text.strip() or "1.0.0"
        author  = self.field_author.text.strip() or "desconhecido"
        desc    = self.field_desc.text.strip() or "Mod exportado do Fox Terminal"
        show_toast(self.result_label, "Gerando .zip...")
        threading.Thread(
            target=self._do_export, args=(name, version, author, desc), daemon=True
        ).start()

    def _do_export(self, name, version, author, desc):
        try:
            os.makedirs(EXPORT_DIR, exist_ok=True)
            mod_dir  = os.path.join(EXPORT_DIR, name)
            zip_path = os.path.join(EXPORT_DIR, f"{name}-{version}.zip")
            os.makedirs(mod_dir, exist_ok=True)

            _save_json(os.path.join(mod_dir, "mod.json"), {
                "name": name, "version": version,
                "author": author, "description": desc,
                "fox_terminal_version": VERSION,
            })

            with open(os.path.join(mod_dir, "README.md"), "w") as f:
                f.write(
                    f"# {name}\n\n"
                    f"**Versao:** {version}  \n**Autor:** {author}  \n"
                    f"**Para:** Fox Terminal {VERSION}\n\n"
                    f"## Descricao\n\n{desc}\n\n"
                    f"## Publicar no GitHub\n\n"
                    f"```bash\ngit init\ngit add .\n"
                    f'git commit -m "Adicionar {name} v{version}"\n'
                    f"git remote add origin https://github.com/{author}/{name}.git\n"
                    f"git push -u origin main\n```\n"
                )

            if os.path.exists(MODS_FILE):
                shutil.copy(MODS_FILE, os.path.join(mod_dir, "fox_mods.json"))

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(mod_dir):
                    zf.write(os.path.join(mod_dir, fname), arcname=fname)

            shutil.rmtree(mod_dir, ignore_errors=True)
            Clock.schedule_once(lambda dt: self._export_done(zip_path))
        except Exception as e:
            Clock.schedule_once(lambda dt: show_toast(self.result_label, f"Erro: {e}"))

    def _export_done(self, zip_path):
        show_toast(self.result_label, "Exportado com sucesso!", duration=4)
        self.instructions.text = (
            f"Arquivo gerado:\n{zip_path}\n\n"
            f"=== Como subir no GitHub ===\n\n"
            f"1. Crie o repositorio em github.com/new\n\n"
            f"2. No terminal Fox execute:\n\n"
            f"   cd {EXPORT_DIR}\n"
            f"   git init\n"
            f"   git add .\n"
            f"   git commit -m \"meu mod\"\n"
            f"   git branch -M main\n"
            f"   git remote add origin https://github.com/USUARIO/REPO.git\n"
            f"   git push -u origin main\n\n"
            f"3. Na aba Releases do repo, anexe o .zip.\n\n"
            f"=== Configurar git ===\n\n"
            f"   git config --global user.email \"email@exemplo.com\"\n"
            f"   git config --global user.name \"SeuNome\"\n"
        )

    def show_github_instructions(self):
        self.instructions.text = (
            "=== Publicar mod no GitHub ===\n\n"
            "Passo 1 - Crie a conta e o repositorio:\n"
            "  Acesse github.com\n"
            "  Clique em New Repository\n"
            "  Nome sugerido: fox-mod-NOMEDOMOD\n\n"
            "Passo 2 - Gere o .zip aqui primeiro:\n"
            "  Preencha os campos e clique Gerar .zip\n\n"
            "Passo 3 - No terminal do Fox:\n\n"
            f"  cd {EXPORT_DIR}\n"
            "  git init\n"
            "  git add .\n"
            "  git commit -m \"primeiro commit\"\n"
            "  git remote add origin https://github.com/USUARIO/REPO.git\n"
            "  git push -u origin main\n\n"
            "Passo 4 - Criar uma Release:\n"
            "  No repositorio, clique em Releases\n"
            "  Clique em Draft a new release\n"
            "  Anexe o arquivo .zip gerado\n\n"
            "Pronto! Outros usuarios podem baixar\n"
            "e instalar seu mod no Fox Terminal.\n"
        )


# ─── App Principal ────────────────────────────────────────────────────────────
class MainApp(MDApp):
    terminal_count  = 1
    mod_python      = False
    mod_node        = False
    mod_git         = False
    mod_file_editor = False

    def build(self):
        self.theme_cls.theme_style     = "Dark"
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.accent_palette  = "BlueGray"

        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(TerminalScreen(1, name="page_1"))
        self.sm.add_widget(StoreScreen(name="store"))
        self.sm.add_widget(ExportScreen(name="export"))
        self.sm.add_widget(PythonEditorScreen(name="python_editor"))
        self.sm.add_widget(PythonConsoleScreen(name="python_console"))
        self.sm.add_widget(NodeReplScreen(name="node_repl"))
        self.sm.add_widget(GitHelperScreen(name="git_helper"))
        self.sm.add_widget(FileEditorScreen(name="file_editor"))
        self.sm.add_widget(VersionManagerScreen(name="version_manager"))

        self.root_layout = BoxLayout(orientation='vertical')
        self.toolbar = MDTopAppBar(
            title=f"Fox Terminal {VERSION}",
            left_action_items=[["menu", lambda x: self.toggle_drawer()]],
            right_action_items=[
                ["plus-box",        lambda x: self.add_terminal()],
                ["package-variant", lambda x: self.set_screen("version_manager")],
                ["export",          lambda x: self.set_screen("export")],
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
        return ui

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

        self.menu_list.add_widget(MDLabel(
            text=f"  Fox Terminal  {VERSION}",
            size_hint_y=None, height="56dp",
            font_style="Caption",
        ))

        for label, icon, screen in [
            ("Nova Aba Terminal",  "plus",            None),
            ("Loja de Mods",       "store",           "store"),
            ("Exportar Mods",      "export",          "export"),
            ("Versoes de Pacotes", "package-variant", "version_manager"),
        ]:
            if screen is None:
                item = OneLineIconListItem(
                    text=label, on_release=lambda x: self.add_terminal()
                )
            else:
                item = OneLineIconListItem(
                    text=label, on_release=lambda x, s=screen: self.set_screen(s)
                )
            item.add_widget(IconLeftWidget(icon=icon))
            self.menu_list.add_widget(item)

        for i in range(1, self.terminal_count + 1):
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
                item = OneLineIconListItem(
                    text=label, on_release=lambda x, s=screen: self.set_screen(s)
                )
                item.add_widget(IconLeftWidget(icon=icon))
                self.menu_list.add_widget(item)

    def set_screen(self, name):
        if name and self.sm.has_screen(name):
            self.sm.current = name
        self.nav_drawer.set_state("close")


if __name__ == "__main__":
    MainApp().run()
