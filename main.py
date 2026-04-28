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
from kivy.uix.codeinput import CodeInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.utils import platform

Window.softinput_mode = 'below_target'

VERSION = "v1.30.0-beta"
HISTORY_FILE = "fox_history.json"
MODS_FILE    = "fox_mods.json"

# Pasta de exportacao — funciona no Android e desktop
if platform == "android":
    try:
        from android.storage import primary_external_storage_path
        EXPORT_DIR = os.path.join(primary_external_storage_path(), "FoxTerminal", "exports")
    except Exception:
        EXPORT_DIR = os.path.join(os.path.expanduser("~"), "FoxTerminal", "exports")
else:
    EXPORT_DIR = os.path.join(os.path.expanduser("~"), "FoxTerminal", "exports")

# Cores suaves
COR_FUNDO       = (0.08, 0.08, 0.10, 1)
COR_FUNDO_INPUT = (0.12, 0.12, 0.15, 1)
COR_TEXTO       = (0.85, 0.90, 0.85, 1)
COR_PROMPT      = (0.45, 0.80, 0.55, 1)
COR_ERRO        = (0.85, 0.45, 0.45, 1)
COR_BARRA       = (0.10, 0.10, 0.14, 1)


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


# ─── Histórico ────────────────────────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history[-200:], f)
    except Exception:
        pass


# ─── Mods (salvar/carregar lista de mods ativos) ──────────────────────────────
def load_mods():
    if os.path.exists(MODS_FILE):
        try:
            with open(MODS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_mod(mod_dict):
    mods = load_mods()
    # evita duplicata pelo nome
    mods = [m for m in mods if m.get("name") != mod_dict.get("name")]
    mods.append(mod_dict)
    try:
        with open(MODS_FILE, "w") as f:
            json.dump(mods, f, indent=2)
    except Exception:
        pass


# ─── Terminal ─────────────────────────────────────────────────────────────────
class TerminalScreen(MDScreen):
    def __init__(self, page_num, **kwargs):
        super().__init__(**kwargs)
        self.name = f"page_{page_num}"
        self.page_num = page_num
        self.cwd = os.path.expanduser("~")
        self.cmd_history = load_history()
        self.history_index = len(self.cmd_history)
        self.process = None

        layout = BoxLayout(orientation='vertical')

        self.progress = MDProgressBar(value=0, size_hint_y=None, height="3dp", opacity=0)

        self.output = CodeInput(
            text=(
                f"Fox Terminal {VERSION}\n"
                f"Terminal {page_num} | Dir: {self.cwd}\n"
                f"$ "
            ),
            readonly=True,
            background_color=COR_FUNDO,
            foreground_color=COR_TEXTO,
            font_size="13sp",
        )

        input_row = BoxLayout(size_hint_y=None, height="48dp", spacing="2dp")

        self.input = TextInput(
            multiline=False,
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            hint_text="Comando...",
            hint_text_color=(0.40, 0.40, 0.40, 1),
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

    def process_command(self, instance):
        cmd = self.input.text.strip()
        self.input.text = ""
        if not cmd:
            return

        if not self.cmd_history or self.cmd_history[-1] != cmd:
            self.cmd_history.append(cmd)
            save_history(self.cmd_history)
        self.history_index = len(self.cmd_history)

        self.output.text += f"$ {cmd}\n"

        if cmd in ("clear", "cls"):
            self.clear_output(None)
            return
        if cmd.startswith("cd "):
            self.change_dir(cmd[3:].strip())
            return
        if cmd == "pwd":
            self.output.text += f"{self.cwd}\n"
            return
        if cmd in ("exit", "quit"):
            MDApp.get_running_app().stop()
            return

        self.progress.opacity = 1
        threading.Thread(target=self.run_sys, args=(cmd,), daemon=True).start()

    def change_dir(self, path):
        new_path = (
            os.path.join(self.cwd, path) if not os.path.isabs(path) else path
        )
        new_path = os.path.normpath(new_path)
        if os.path.isdir(new_path):
            self.cwd = new_path
            self.output.text += f"-> {self.cwd}\n"
        else:
            self.output.text += f"cd: {path}: nao encontrado\n"

    def run_sys(self, cmd):
        try:
            self.process = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=self.cwd
            )
            out, err = self.process.communicate(timeout=60)
            code = self.process.returncode
            Clock.schedule_once(lambda dt: self.done(out, err, code))
        except subprocess.TimeoutExpired:
            self.process.kill()
            Clock.schedule_once(
                lambda dt: self.done("", "Tempo limite (60s) excedido\n", 1)
            )
        except Exception as e:
            Clock.schedule_once(lambda dt: self.done("", str(e), 1))
        finally:
            self.process = None

    def done(self, out, err, code):
        if out:
            self.output.text += out
        if err:
            self.output.text += f"[erro] {err}\n"
        status = "[ok]" if code == 0 else f"[falhou: {code}]"
        self.output.text += f"{status}\n$ "
        self.progress.opacity = 0

    def stop_process(self, instance):
        if self.process:
            try:
                self.process.kill()
                self.output.text += "\n[processo encerrado]\n$ "
            except Exception:
                pass
        else:
            self.output.text += "[sem processo ativo]\n$ "

    def clear_output(self, instance):
        self.output.text = (
            f"Fox Terminal {VERSION} - Terminal {self.page_num}\n$ "
        )


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
            ("language-python", "Python Editor - editor + console integrado", "python_editor"),
            ("language-javascript", "Node.js REPL - execute JS (em breve)", None),
            ("git", "Git Helper - atalhos Git (em breve)", None),
            ("file-code", "Editor de Arquivos - .txt/.py (em breve)", None),
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

        btn_row = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp",
                            padding=("8dp", 0))
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
        if screen_name == "python_editor":
            app.python_installed = True
            app.update_menu()
            save_mod({"name": "python_editor", "title": "Python Editor",
                      "version": "1.0", "author": "Fox Terminal"})
            show_toast(self.msg_label, "Mod Python ativado!")
        else:
            show_toast(self.msg_label, "Em breve!")


# ─── Tela de Exportacao de Mods ───────────────────────────────────────────────
class ExportScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding="16dp", spacing="10dp")

        layout.add_widget(MDLabel(
            text="Exportar Mods",
            font_style="H5", halign="center",
            size_hint_y=None, height="48dp"
        ))

        layout.add_widget(MDLabel(
            text="Nome do mod (sem espacos):",
            size_hint_y=None, height="28dp",
            theme_text_color="Secondary",
        ))
        self.field_name = TextInput(
            text="meu_mod",
            multiline=False,
            size_hint_y=None, height="44dp",
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="14sp",
        )
        layout.add_widget(self.field_name)

        layout.add_widget(MDLabel(
            text="Versao:",
            size_hint_y=None, height="28dp",
            theme_text_color="Secondary",
        ))
        self.field_version = TextInput(
            text="1.0.0",
            multiline=False,
            size_hint_y=None, height="44dp",
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            font_size="14sp",
        )
        layout.add_widget(self.field_version)

        layout.add_widget(MDLabel(
            text="Autor (seu usuario GitHub):",
            size_hint_y=None, height="28dp",
            theme_text_color="Secondary",
        ))
        self.field_author = TextInput(
            text="",
            multiline=False,
            size_hint_y=None, height="44dp",
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            hint_text="ex: seuusuario",
            hint_text_color=(0.4, 0.4, 0.4, 1),
            font_size="14sp",
        )
        layout.add_widget(self.field_author)

        layout.add_widget(MDLabel(
            text="Descricao:",
            size_hint_y=None, height="28dp",
            theme_text_color="Secondary",
        ))
        self.field_desc = TextInput(
            text="",
            multiline=True,
            size_hint_y=None, height="72dp",
            background_color=COR_FUNDO_INPUT,
            foreground_color=COR_TEXTO,
            cursor_color=COR_PROMPT,
            hint_text="O que este mod faz?",
            hint_text_color=(0.4, 0.4, 0.4, 1),
            font_size="13sp",
        )
        layout.add_widget(self.field_desc)

        # Resultado / log da exportacao
        self.result_label = MDLabel(
            text="",
            halign="center",
            size_hint_y=None, height="48dp",
            theme_text_color="Secondary",
            font_style="Caption",
        )
        layout.add_widget(self.result_label)

        btn_row = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        btn_row.add_widget(MDRaisedButton(
            text="Gerar .zip",
            on_release=self.export_zip
        ))
        btn_row.add_widget(MDRaisedButton(
            text="Ver instrucoes GitHub",
            on_release=lambda x: self.show_github_instructions()
        ))
        btn_row.add_widget(MDRaisedButton(
            text="Voltar",
            on_release=lambda x: MDApp.get_running_app().set_screen("store")
        ))
        layout.add_widget(btn_row)

        scroll = ScrollView()
        self.instructions = CodeInput(
            text="",
            readonly=True,
            background_color=COR_FUNDO,
            foreground_color=COR_TEXTO,
            font_size="12sp",
        )
        scroll.add_widget(self.instructions)
        layout.add_widget(scroll)

        self.add_widget(layout)

    def export_zip(self, instance):
        name    = self.field_name.text.strip().replace(" ", "_") or "meu_mod"
        version = self.field_version.text.strip() or "1.0.0"
        author  = self.field_author.text.strip() or "desconhecido"
        desc    = self.field_desc.text.strip() or "Mod exportado do Fox Terminal"

        # Tudo em thread para nao travar a UI
        threading.Thread(
            target=self._do_export,
            args=(name, version, author, desc),
            daemon=True
        ).start()
        show_toast(self.result_label, "Gerando .zip...")

    def _do_export(self, name, version, author, desc):
        try:
            os.makedirs(EXPORT_DIR, exist_ok=True)
            mod_dir  = os.path.join(EXPORT_DIR, name)
            zip_path = os.path.join(EXPORT_DIR, f"{name}-{version}.zip")

            os.makedirs(mod_dir, exist_ok=True)

            # Arquivo de metadados do mod
            meta = {
                "name":        name,
                "version":     version,
                "author":      author,
                "description": desc,
                "fox_terminal_version": VERSION,
            }
            with open(os.path.join(mod_dir, "mod.json"), "w") as f:
                json.dump(meta, f, indent=2)

            # README automatico
            readme = (
                f"# {name}\n\n"
                f"**Versao:** {version}  \n"
                f"**Autor:** {author}  \n"
                f"**Para:** Fox Terminal {VERSION}\n\n"
                f"## Descricao\n\n{desc}\n\n"
                f"## Como instalar\n\n"
                f"1. Baixe o arquivo `.zip`\n"
                f"2. Abra o Fox Terminal\n"
                f"3. Va em Loja de Mods > Importar\n"
                f"4. Selecione o arquivo `.zip`\n\n"
                f"## Como publicar no GitHub\n\n"
                f"```bash\n"
                f"git init\n"
                f"git add .\n"
                f'git commit -m "Adicionar mod {name} v{version}"\n'
                f"git remote add origin https://github.com/{author}/{name}.git\n"
                f"git push -u origin main\n"
                f"```\n"
            )
            with open(os.path.join(mod_dir, "README.md"), "w") as f:
                f.write(readme)

            # Salva tambem o fox_mods.json atual junto
            mods_src = MODS_FILE
            if os.path.exists(mods_src):
                shutil.copy(mods_src, os.path.join(mod_dir, "fox_mods.json"))

            # Compactar tudo em .zip
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(mod_dir):
                    zf.write(os.path.join(mod_dir, fname), arcname=fname)

            # Limpar pasta temporaria
            shutil.rmtree(mod_dir, ignore_errors=True)

            msg = f"Salvo em:\n{zip_path}"
            Clock.schedule_once(lambda dt: self._export_done(msg, zip_path), 0)

        except Exception as e:
            msg = f"Erro: {str(e)}"
            Clock.schedule_once(lambda dt: show_toast(self.result_label, msg), 0)

    def _export_done(self, msg, zip_path):
        show_toast(self.result_label, "Exportado com sucesso!", duration=4)
        self.instructions.text = (
            f"Arquivo gerado:\n{zip_path}\n\n"
            f"=== Como subir no GitHub ===\n\n"
            f"1. Crie um repositorio no GitHub\n"
            f"   -> github.com/new\n\n"
            f"2. No terminal do Fox, rode:\n\n"
            f"   cd {EXPORT_DIR}\n"
            f"   git init\n"
            f"   git add .\n"
            f'   git commit -m "meu mod fox terminal"\n'
            f"   git branch -M main\n"
            f"   git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git\n"
            f"   git push -u origin main\n\n"
            f"3. O arquivo .zip estara disponivel\n"
            f"   na aba Releases do seu repo.\n\n"
            f"=== Dica ===\n"
            f"Se o git pedir autenticacao use:\n"
            f"   git config --global user.email 'email@exemplo.com'\n"
            f"   git config --global user.name 'SeuNome'\n"
        )

    def show_github_instructions(self):
        self.instructions.text = (
            "=== Publicar mod no GitHub ===\n\n"
            "Passo 1 — Crie a conta e o repo:\n"
            "  -> Acesse github.com\n"
            "  -> Clique em New Repository\n"
            "  -> Nome sugerido: fox-mod-NOMEDOMOD\n\n"
            "Passo 2 — Gere o .zip aqui primeiro\n"
            "  -> Clique em 'Gerar .zip'\n\n"
            "Passo 3 — No terminal do Fox:\n\n"
            f"  cd {EXPORT_DIR}\n"
            "  git init\n"
            "  git add .\n"
            '  git commit -m "primeiro commit"\n'
            "  git remote add origin https://github.com/USUARIO/REPO.git\n"
            "  git push -u origin main\n\n"
            "Passo 4 — Criar uma Release no GitHub:\n"
            " 
