import subprocess
import platform
import json
import os
import time
import threading
import urllib.request

from gear_xls.runtime_paths import (
    HEALTH_MARKER,
    get_project_root_id,
    get_server_health_url,
)

FLASK_SERVER_MARKER = HEALTH_MARKER


class ProcessManager:
    """Управление процессами и терминалами"""
    
    def __init__(self):
        self.terminal_process = None
        self.flask_process = None
    
    def execute_command_and_wait(self, commands, directory=None):
        """Выполняет команды и ждет их завершения (без интерактивного терминала)"""
        if not directory:
            return None
        
        system = platform.system()
        
        try:
            if system == "Windows":
                # Для Windows объединяем команды с помощью &
                full_command = " & ".join(commands)
                cmd = f"cd /d {directory} & {full_command}"
                return subprocess.Popen(cmd, shell=True, cwd=directory)
            
            else:  # Unix-подобные системы
                # Создаем команду для выполнения
                full_command = " && ".join([f"cd '{directory}'"] + commands)
                return subprocess.Popen(full_command, shell=True, cwd=directory)
                
        except Exception as e:
            print(f"Ошибка при выполнении команды: {e}")
            return None

    def execute_command_capture(self, commands, directory, log_callback):
        """
        Выполняет команды, перехватывает stdout+stderr и передает строки в log_callback.
        Возвращает кортеж (process, reader_thread). Вызывающий код должен дождаться
        завершения process.wait() и reader_thread.join().
        """
        import threading

        if not directory:
            return None, None

        system = platform.system()

        try:
            if system == "Windows":
                full_command = " & ".join(commands)
                # Quotes are required because directory may contain spaces.
                cmd = f'cd /d "{directory}" & {full_command}'
            else:
                full_command = " && ".join([f"cd '{directory}'"] + commands)
                cmd = full_command

            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            def _reader(p, cb):
                try:
                    if not p.stdout:
                        return
                    for line in iter(p.stdout.readline, ""):
                        stripped = line.rstrip()
                        if stripped:
                            cb(stripped)
                finally:
                    if p.stdout:
                        p.stdout.close()

            reader_thread = threading.Thread(
                target=_reader,
                args=(proc, log_callback),
                daemon=True,
            )
            reader_thread.start()

            return proc, reader_thread

        except Exception as e:
            print(f"Ошибка при запуске процесса с захватом вывода: {e}")
            return None, None

    def is_process_running(self, process):
        """Проверяет, активен ли процесс"""
        if not process:
            return False
        try:
            return process.poll() is None
        except:
            return False
    
    def is_flask_server_running(self, project_root=None, url=None, timeout=1.0):
        """Check whether the expected Flask server responds on localhost."""
        if url is None:
            url = get_server_health_url(project_root)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                body = response.read(2048).decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                if project_root is not None:
                    return (
                        isinstance(data, dict)
                        and data.get("ok") is True
                        and data.get("marker") == FLASK_SERVER_MARKER
                        and data.get("project_root_id") == get_project_root_id(project_root)
                    )
                return (
                    isinstance(data, dict)
                    and data.get("ok") is True
                    and data.get("marker") == FLASK_SERVER_MARKER
                )
            except json.JSONDecodeError:
                return FLASK_SERVER_MARKER in body and project_root is None
        except Exception:
            return False

    def wait_for_flask_server(self, project_root=None, timeout=5.0, poll_interval=0.3):
        """Wait for the Flask server to become reachable."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_flask_server_running(project_root):
                return True
            time.sleep(poll_interval)
        return False

    def get_terminal_command(self):
        """Возвращает команду для запуска терминала в зависимости от ОС"""
        if platform.system() == "Windows":
            return ["cmd.exe", "/K"]
        elif platform.system() == "Darwin":  # macOS
            return ["open", "-a", "Terminal"]
        else:  # Linux и др.
            # Проверяем наличие различных терминалов
            terminals = ["gnome-terminal", "xterm", "konsole"]
            for term in terminals:
                try:
                    subprocess.run(["which", term], capture_output=True, text=True, check=False)
                    if term == "gnome-terminal":
                        return [term, "--"]
                    else:
                        return [term, "-e"]
                except:
                    continue
            # Если ни один из известных терминалов не найден
            return ["x-terminal-emulator", "-e"]
    
    def execute_in_terminal(self, commands, directory=None):
        """Выполняет команды в терминале"""
        if not directory:
            return None
        
        system = platform.system()
        
        if system == "Windows":
            # Для Windows объединяем команды с помощью & 
            full_command = " & ".join(commands)
            cmd = ["cmd.exe", "/K", f"cd /d {directory} & {full_command}"]
            return subprocess.Popen(cmd)
        
        elif system == "Darwin":  # macOS
            # Создаем скрипт с командами
            script_path = os.path.join(os.path.expanduser("~"), "temp_commands.sh")
            with open(script_path, "w") as script:
                script.write("#!/bin/bash\n")
                script.write(f"cd \"{directory}\"\n")
                for cmd in commands:
                    script.write(f"{cmd}\n")
            
            # Делаем скрипт исполняемым
            os.chmod(script_path, 0o755)
            
            # Запускаем Terminal с нашим скриптом
            return subprocess.Popen(["open", "-a", "Terminal", script_path])
        
        else:  # Linux и др.
            # Подобно macOS, создаем временный скрипт
            script_path = os.path.join("/tmp", "temp_commands.sh")
            with open(script_path, "w") as script:
                script.write("#!/bin/bash\n")
                script.write(f"cd \"{directory}\"\n")
                for cmd in commands:
                    script.write(f"{cmd}\n")
                script.write("bash\n")  # Оставляем оболочку открытой
            
            # Делаем скрипт исполняемым
            os.chmod(script_path, 0o755)
            
            # Определяем доступный терминал
            terminal_cmd = self.get_terminal_command()
            
            if terminal_cmd[0] == "gnome-terminal":
                return subprocess.Popen(terminal_cmd + [f"bash -c '{script_path}; bash'"])
            else:
                return subprocess.Popen(terminal_cmd + [f"bash {script_path}"])
    
    def start_new_terminal_with_commands(self, program_directory):
        """Запускает новый терминал с командами для flask-сервера"""
        system = platform.system()
        
        if system == "Windows":
            # Для Windows создаем bat-файл с правильным рабочим каталогом
            bat_file = os.path.join(program_directory, "start_flask.bat")
            
            # Создаем bat-файл, который установит правильный рабочий каталог
            with open(bat_file, "w") as f:
                f.write(f'@echo off\n')
                f.write(f'cd /d "{program_directory}"\n')
                f.write(f'cd /d gear_xls\n')
                f.write(f'python server_routes.py\n')
                f.write(f'pause\n')  # Пауза, чтобы окно не закрывалось
            
            # Запускаем новое окно cmd с bat-файлом
            cmd = ["cmd.exe", "/C", f"start cmd /K {bat_file}"]
            return subprocess.Popen(cmd, cwd=program_directory)
        
        elif system == "Darwin":  # macOS
            # Создаем AppleScript для открытия нового Terminal
            script = f'''
            tell application "Terminal"
                do script "cd '{program_directory}' && python gear_xls/server_routes.py"
                activate
            end tell
            '''
            return subprocess.Popen(['osascript', '-e', script])
        
        else:  # Linux и другие Unix-подобные системы
            # Пробуем различные терминалы Linux
            terminals = [
                ("gnome-terminal", ["gnome-terminal", "--", "bash", "-c", f"cd '{program_directory}' && python gear_xls/server_routes.py; read"]),
                ("xterm", ["xterm", "-e", f"cd '{program_directory}' && python gear_xls/server_routes.py; read"]),
                ("konsole", ["konsole", "-e", f"cd '{program_directory}' && python gear_xls/server_routes.py; read"]),
                ("x-terminal-emulator", ["x-terminal-emulator", "-e", f"cd '{program_directory}' && python gear_xls/server_routes.py; read"])
            ]
            
            for term_name, cmd in terminals:
                try:
                    # Проверяем, доступен ли терминал
                    subprocess.run(["which", term_name], capture_output=True, text=True, check=True)
                    return subprocess.Popen(cmd)
                except:
                    continue
            
            # Если ничего не работает, возвращаемся к стандартному способу
            return subprocess.Popen(["bash", "-c", f"cd '{program_directory}' && python gear_xls/server_routes.py"])
