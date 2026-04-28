from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.properties import StringProperty, ListProperty
from kivy.utils import platform

import subprocess
import threading
import json
import zipfile
import shutil
import os
import sys
import io

# KivyMD imports
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.toolbar import MDToolbar
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.label import MDLabel
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.toast import toast

# Permissions for Android
if platform == 'android':
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path

class TerminalScreen(MDScreen):
    output_text = StringProperty('')
    current_dir = StringProperty(os.path.expanduser('~'))
    history = ListProperty([])
    history_index = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dialog = None
        self.file_manager = None
        self.request_android_permissions()
        Clock.schedule_once(self.setup_ui, 0)

    def request_android_permissions(self):
        if platform == 'android':
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

    def setup_ui(self, dt):
        self.ids.toolbar.title = f"Fox Terminal - {self.current_dir}"
        self.update_output("Bem-vindo ao Fox Terminal!\n")
        self.update_output(f"Diretório atual: {self.current_dir}\n")

    def on_enter(self):
        self.ids.command_input.focus = True

    def execute_command(self, instance):
        command = self.ids.command_input.text.strip()
        self.ids.command_input.text = ''
        if not command:
            return

        self.history.append(command)
        self.history_index = len(self.history)

        self.update_output(f"\n$ {command}\n")

        if command.lower() == 'clear':
            self.output_text = ''
            self.update_output(f"Diretório atual: {self.current_dir}\n")
            return
        elif command.lower() == 'exit':
            App.get_running_app().stop()
            return
        elif command.lower().startswith('cd '):
            self.change_directory(command[3:].strip())
            return
        elif command.lower() == 'ls' or command.lower() == 'dir':
            self.list_directory()
            return
        elif command.lower().startswith('cat '):
            self.view_file(command[4:].strip())
            return
        elif command.lower().startswith('mkdir '):
            self.create_directory(command[6:].strip())
            return
        elif command.lower().startswith('rmdir '):
            self.remove_directory(command[6:].strip())
            return
        elif command.lower().startswith('rm '):
            self.remove_file(command[3:].strip())
            return
        elif command.lower().startswith('touch '):
            self.create_file(command[6:].strip())
            return
        elif command.lower().startswith('echo '):
            parts = command[5:].split(' > ')
            if len(parts) == 2:
                self.echo_to_file(parts[0], parts[1])
            else:
                self.update_output(parts[0] + '\n')
            return
        elif command.lower().startswith('zip '):
            parts = command[4:].split(' ')
            if len(parts) == 2:
                self.zip_file_or_folder(parts[0], parts[1])
            else:
                self.update_output("Uso: zip <origem> <destino.zip>\n")
            return
        elif command.lower().startswith('unzip '):
            parts = command[6:].split(' ')
            if len(parts) == 2:
                self.unzip_file_or_folder(parts[0], parts[1])
            else:
                self.update_output("Uso: unzip <arquivo.zip> <destino>\n")
            return
        elif command.lower().startswith('cp '):
            parts = command[3:].split(' ')
            if len(parts) == 2:
                self.copy_item(parts[0], parts[1])
            else:
                self.update_output("Uso: cp <origem> <destino>\n")
            return
        elif command.lower().startswith('mv '):
            parts = command[3:].split(' ')
            if len(parts) == 2:
                self.move_item(parts[0], parts[1])
            else:
                self.update_output("Uso: mv <origem> <destino>\n")
            return
        elif command.lower().startswith('find '):
            self.find_files(command[5:].strip())
            return
        elif command.lower().startswith('grep '):
            parts = command[5:].split(' ')
            if len(parts) >= 2:
                self.grep_file(parts[0], ' '.join(parts[1:]))
            else:
                self.update_output("Uso: grep <padrão> <arquivo>\n")
            return
        elif command.lower() == 'help':
            self.show_help()
            return
        else:
            self.run_external_command(command)

    def run_external_command(self, command):
        def target():
            try:
                process = subprocess.Popen(
                    command, 
                    shell=True, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    cwd=self.current_dir,
                    text=True, # Decode stdout/stderr as text
                    encoding='utf-8' # Specify encoding
                )
                stdout, stderr = process.communicate()
                output = stdout + stderr
                Clock.schedule_once(lambda dt: self.update_output(output), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.update_output(f"Erro: {e}\n"), 0)

        threading.Thread(target=target).start()

    def update_output(self, text):
        self.output_text += text
        self.ids.scroll_view.scroll_to(self.ids.output_label)

    def change_directory(self, path):
        try:
            new_path = os.path.abspath(os.path.join(self.current_dir, path))
            if os.path.isdir(new_path):
                self.current_dir = new_path
                self.ids.toolbar.title = f"Fox Terminal - {self.current_dir}"
                self.update_output(f"Diretório alterado para: {self.current_dir}\n")
            else:
                self.update_output(f"Erro: Diretório '{path}' não encontrado.\n")
        except Exception as e:
            self.update_output(f"Erro ao mudar de diretório: {e}\n")

    def list_directory(self):
        try:
            files = os.listdir(self.current_dir)
            output = "\n".join(files) + "\n"
            self.update_output(output)
        except Exception as e:
            self.update_output(f"Erro ao listar diretório: {e}\n")

    def view_file(self, filename):
        filepath = os.path.join(self.current_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                self.update_output(content + '\n')
        except FileNotFoundError:
            self.update_output(f"Erro: Arquivo '{filename}' não encontrado.\n")
        except Exception as e:
            self.update_output(f"Erro ao ler arquivo: {e}\n")

    def create_directory(self, dirname):
        dirpath = os.path.join(self.current_dir, dirname)
        try:
            os.makedirs(dirpath)
            self.update_output(f"Diretório '{dirname}' criado com sucesso.\n")
        except FileExistsError:
            self.update_output(f"Erro: Diretório '{dirname}' já existe.\n")
        except Exception as e:
            self.update_output(f"Erro ao criar diretório: {e}\n")

    def remove_directory(self, dirname):
        dirpath = os.path.join(self.current_dir, dirname)
        try:
            os.rmdir(dirpath)
            self.update_output(f"Diretório '{dirname}' removido com sucesso.\n")
        except FileNotFoundError:
            self.update_output(f"Erro: Diretório '{dirname}' não encontrado.\n")
        except OSError as e:
            self.update_output(f"Erro: O diretório '{dirname}' não está vazio ou é um arquivo. Use 'rm' para arquivos ou 'rm -r' para diretórios não vazios (não implementado).\n")
        except Exception as e:
            self.update_output(f"Erro ao remover diretório: {e}\n")

    def remove_file(self, filename):
        filepath = os.path.join(self.current_dir, filename)
        try:
            os.remove(filepath)
            self.update_output(f"Arquivo '{filename}' removido com sucesso.\n")
        except FileNotFoundError:
            self.update_output(f"Erro: Arquivo '{filename}' não encontrado.\n")
        except Exception as e:
            self.update_output(f"Erro ao remover arquivo: {e}\n")

    def create_file(self, filename):
        filepath = os.path.join(self.current_dir, filename)
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                pass # Just create or touch the file
            self.update_output(f"Arquivo '{filename}' criado com sucesso.\n")
        except Exception as e:
            self.update_output(f"Erro ao criar arquivo: {e}\n")

    def echo_to_file(self, text, filename):
        filepath = os.path.join(self.current_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text + '\n')
            self.update_output(f"Texto escrito em '{filename}'.\n")
        except Exception as e:
            self.update_output(f"Erro ao escrever no arquivo: {e}\n")

    def zip_file_or_folder(self, source, destination_zip):
        source_path = os.path.join(self.current_dir, source)
        destination_zip_path = os.path.join(self.current_dir, destination_zip)
        try:
            if os.path.isfile(source_path):
                with zipfile.ZipFile(destination_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(source_path, os.path.basename(source_path))
                self.update_output(f"Arquivo '{source}' compactado para '{destination_zip}'.\n")
            elif os.path.isdir(source_path):
                shutil.make_archive(os.path.splitext(destination_zip_path)[0], 'zip', source_path)
                self.update_output(f"Pasta '{source}' compactada para '{destination_zip}'.\n")
            else:
                self.update_output(f"Erro: Origem '{source}' não encontrada ou não é um arquivo/diretório válido.\n")
        except Exception as e:
            self.update_output(f"Erro ao compactar: {e}\n")

    def unzip_file_or_folder(self, source_zip, destination_folder):
        source_zip_path = os.path.join(self.current_dir, source_zip)
        destination_folder_path = os.path.join(self.current_dir, destination_folder)
        try:
            with zipfile.ZipFile(source_zip_path, 'r') as zipf:
                zipf.extractall(destination_folder_path)
            self.update_output(f"Arquivo '{source_zip}' descompactado para '{destination_folder}'.\n")
        except FileNotFoundError:
            self.update_output(f"Erro: Arquivo ZIP '{source_zip}' não encontrado.\n")
        except Exception as e:
            self.update_output(f"Erro ao descompactar: {e}\n")

    def copy_item(self, source, destination):
        source_path = os.path.join(self.current_dir, source)
        destination_path = os.path.join(self.current_dir, destination)
        try:
            if os.path.isfile(source_path):
                shutil.copy2(source_path, destination_path)
                self.update_output(f"Arquivo '{source}' copiado para '{destination}'.\n")
            elif os.path.isdir(source_path):
                shutil.copytree(source_path, destination_path)
                self.update_output(f"Pasta '{source}' copiada para '{destination}'.\n")
            else:
                self.update_output(f"Erro: Origem '{source}' não encontrada ou não é um arquivo/diretório válido.\n")
        except Exception as e:
            self.update_output(f"Erro ao copiar: {e}\n")

    def move_item(self, source, destination):
        source_path = os.path.join(self.current_dir, source)
        destination_path = os.path.join(self.current_dir, destination)
        try:
            shutil.move(source_path, destination_path)
            self.update_output(f"'{source}' movido para '{destination}'.\n")
        except FileNotFoundError:
            self.update_output(f"Erro: Origem '{source}' não encontrada.\n")
        except Exception as e:
            self.update_output(f"Erro ao mover: {e}\n")

    def find_files(self, name_pattern):
        found_files = []
        for root, _, files in os.walk(self.current_dir):
            for file in files:
                if name_pattern in file:
                    found_files.append(os.path.join(root, file))
        if found_files:
            self.update_output("\n".join(found_files) + '\n')
        else:
            self.update_output(f"Nenhum arquivo encontrado com o padrão '{name_pattern}'.\n")

    def grep_file(self, pattern, filename):
        filepath = os.path.join(self.current_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                found_lines = [line.strip() for line in lines if pattern in line]
                if found_lines:
                    self.update_output("\n".join(found_lines) + '\n')
                else:
                    self.update_output(f"Nenhum resultado encontrado para '{pattern}' em '{filename}'.\n")
        except FileNotFoundError:
            self.update_output(f"Erro: Arquivo '{filename}' não encontrado.\n")
        except Exception as e:
            self.update_output(f"Erro ao buscar no arquivo: {e}\n")

    def show_help(self):
        help_message = """
Comandos disponíveis:
  clear                  - Limpa a tela do terminal.
  exit                   - Sai do aplicativo.
  cd <diretório>         - Muda o diretório atual.
  ls / dir               - Lista o conteúdo do diretório atual.
  cat <arquivo>          - Exibe o conteúdo de um arquivo.
  mkdir <diretório>      - Cria um novo diretório.
  rmdir <diretório>      - Remove um diretório vazio.
  rm <arquivo>           - Remove um arquivo.
  touch <arquivo>        - Cria um arquivo vazio.
  echo <texto> [> <arquivo>] - Exibe texto ou escreve em um arquivo.
  zip <origem> <destino.zip> - Compacta arquivo/pasta.
  unzip <arquivo.zip> <destino> - Descompacta arquivo/pasta.
  cp <origem> <destino>  - Copia arquivo/pasta.
  mv <origem> <destino>  - Move arquivo/pasta.
  find <padrão>          - Encontra arquivos pelo nome no diretório atual e subdiretórios.
  grep <padrão> <arquivo> - Busca por um padrão em um arquivo.
  help                   - Exibe esta mensagem de ajuda.
Qualquer outro comando será executado via subprocesso (se disponível no Android).
        """
        self.update_output(help_message + '\n')

    def on_history_up(self):
        if self.history and self.history_index > 0:
            self.history_index -= 1
            self.ids.command_input.text = self.history[self.history_index]

    def on_history_down(self):
        if self.history and self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.ids.command_input.text = self.history[self.history_index]
        elif self.history and self.history_index == len(self.history) - 1:
            self.history_index = len(self.history)
            self.ids.command_input.text = ''


class FoxTerminalApp(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "BlueGray"
        self.theme_cls.theme_style = "Dark"
        return TerminalScreen()

    def on_start(self):
        # Request permissions on start if not already granted
        if platform == 'android':
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

if __name__ == '__main__':
    FoxTerminalApp().run()

